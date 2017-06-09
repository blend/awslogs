import re
import sys
import os
import time
import errno
import yaml
import pystache
from datetime import datetime, timedelta
from collections import deque
from .aws_log_generator import AWSLogGenerator
from .logprinter import LogPrinter
from .querytemplate import QueryTemplate

import boto3
from botocore.compat import json, six, total_seconds

from dateutil.parser import parse
from dateutil.tz import tzutc

from . import exceptions

class AWSLogs(object):

    FILTER_LOG_EVENTS_STREAMS_LIMIT = 100
    MAX_EVENTS_PER_CALL = 10000

    # TODO separate out the required options for each subcommand
    def __init__(self, **kwargs):
        valid_output_options = ('color_enabled', 'output_stream_enabled', 'output_group_enabled',
                          'output_timestamp_enabled', 'output_ingestion_time_enabled',
                          'query')

        self.output_options = {k:v for k, v in kwargs.iteritems() if k in valid_output_options}
        self.aws_region = kwargs.get('aws_region')
        self.aws_access_key_id = kwargs.get('aws_access_key_id')
        self.aws_secret_access_key = kwargs.get('aws_secret_access_key')
        self.aws_session_token = kwargs.get('aws_session_token')
        self.log_group_name = kwargs.get('log_group_name')
        self.log_stream_prefix = kwargs.get('log_stream_prefix')
        self.filter_pattern = kwargs.get('filter_pattern')
        self.watch = kwargs.get('watch')
        self.start = self.parse_datetime(kwargs.get('start'))
        self.end = self.parse_datetime(kwargs.get('end'))
        self.query = kwargs.get('query')
        self.query_template_file = kwargs.get('query_template_file')
        self.query_template_args = kwargs.get('args')

        self.log_group_prefix = kwargs.get('log_group_prefix')
        self.client = boto3.client(
            'logs',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            aws_session_token=self.aws_session_token,
            region_name=self.aws_region
        )


    def list_logs(self):
        streams = list(self.get_streams(self.log_group_name, self.log_stream_prefix))
        if len(streams) > self.FILTER_LOG_EVENTS_STREAMS_LIMIT:
            raise exceptions.TooManyStreamsFilteredError(
                 self.log_stream_name,
                 len(streams),
                 self.FILTER_LOG_EVENTS_STREAMS_LIMIT
            )
        elif len(streams) == 0:
            raise exceptions.NoStreamsFilteredError(self.log_stream_prefix)


        # Note: filter_log_events paginator is broken
        # ! Error during pagination: The same next token was received twice
        do_wait = object()
        aws_log_generator = AWSLogGenerator(log_group_name=self.log_group_name,
                                            log_streams=streams,
                                            start_time=self.start,
                                            filter_pattern=self.filter_pattern) # TODO add end time

        max_stream_length = max([len(s) for s in streams]) if streams else 10
        log_printer = LogPrinter(self.log_group_name, max_stream_length, **self.output_options)
        try:
            aws_log_generator.get_and_print_logs(self.client, log_printer)
        except KeyboardInterrupt:
            print('Closing...\n')
            os._exit(0)

    def list_groups(self):
        """Lists available CloudWatch logs groups"""
        for group in self.get_groups():
            print(group)

    def list_streams(self):
        """Lists available CloudWatch logs streams in ``log_group_name``."""
        for stream in self.get_streams(self.log_group_name):
            print(stream)

    def get_groups(self):
        """Returns available CloudWatch logs groups"""
        kwargs = {}
        if self.log_group_prefix is not None:
            kwargs = {'logGroupNamePrefix': self.log_group_prefix}
        paginator = self.client.get_paginator('describe_log_groups')
        for page in paginator.paginate(**kwargs):
            for group in page.get('logGroups', []):
                yield group['logGroupName']

    def get_streams(self, log_group_name, log_stream_prefix = None):
        """Returns available CloudWatch logs streams in ``log_group_name``."""
        kwargs = {'logGroupName': log_group_name}
        if log_stream_prefix is not None:
            kwargs['logStreamNamePrefix'] = log_stream_prefix
        window_start = self.start or 0
        window_end = self.end or sys.float_info.max

        paginator = self.client.get_paginator('describe_log_streams')
        for page in paginator.paginate(**kwargs):
            for stream in page.get('logStreams', []):
                if 'firstEventTimestamp' not in stream:
                    # This is a specified log stream rather than
                    # a filter on the whole log group, so there's
                    # no firstEventTimestamp.
                    yield stream['logStreamName']
                elif max(stream['firstEventTimestamp'], window_start) <= \
                        min(stream['lastEventTimestamp'], window_end):
                    yield stream['logStreamName']

    # TODO clean this up
    def query_logs_by_template(self):
        print 'in query_logs_by_template'
        print 'query_template_file: {}'.format(self.query_template_file)




        query_template = QueryTemplate(self.query_template_file, self.query_template_args)
        print query_template.log_group_name
        streams = list(self.get_streams(query_template.log_group_name, query_template.log_stream_prefix))
        print 'got streams {}'.format(streams)

        aws_log_generator = AWSLogGenerator(log_group_name=query_template.log_group_name,
                                            log_streams=streams,
                                            start_time=self.parse_datetime('1d'),
                                            filter_pattern=query_template.filter_pattern)

        print 'some aws log generator: {}'.format(aws_log_generator)
        max_stream_length = max([len(s) for s in streams]) if streams else 10
        log_printer = LogPrinter(query_template.log_group_name, max_stream_length, **self.output_options)
        aws_log_generator.get_and_print_logs(self.client, log_printer)

        raise Exception("got to the end breh")



    def parse_datetime(self, datetime_text):
        """Parse ``datetime_text`` into a ``datetime``."""

        if not datetime_text:
            return None

        ago_regexp = r'(\d+)\s?(m|minute|minutes|h|hour|hours|d|day|days|w|weeks|weeks)(?: ago)?'
        ago_match = re.match(ago_regexp, datetime_text)

        if ago_match:
            amount, unit = ago_match.groups()
            amount = int(amount)
            unit = {'m': 60, 'h': 3600, 'd': 86400, 'w': 604800}[unit[0]]
            date = datetime.utcnow() + timedelta(seconds=unit * amount * -1)
        else:
            try:
                date = parse(datetime_text)
            except ValueError:
                raise exceptions.UnknownDateError(datetime_text)

        if date.tzinfo:
            if date.utcoffset != 0:
                date = date.astimezone(tzutc())
            date = date.replace(tzinfo=None)

        return int(total_seconds(date - datetime(1970, 1, 1))) * 1000
