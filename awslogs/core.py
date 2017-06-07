import re
import sys
import os
import time
import errno
from datetime import datetime, timedelta
from collections import deque

import boto3
from botocore.compat import json, six, total_seconds

import jmespath

from termcolor import colored
from dateutil.parser import parse
from dateutil.tz import tzutc

from . import exceptions


def milis2iso(milis):
    res = datetime.utcfromtimestamp(milis/1000.0).isoformat()
    return (res + ".000")[:23] + 'Z'


class AWSLogs(object):

    ACTIVE = 1
    EXHAUSTED = 2
    WATCH_SLEEP = 2

    FILTER_LOG_EVENTS_STREAMS_LIMIT = 100
    MAX_EVENTS_PER_CALL = 10000
    ALL_WILDCARD = 'ALL'

    def __init__(self, **kwargs):
        self.aws_region = kwargs.get('aws_region')
        self.aws_access_key_id = kwargs.get('aws_access_key_id')
        self.aws_secret_access_key = kwargs.get('aws_secret_access_key')
        self.aws_session_token = kwargs.get('aws_session_token')
        self.log_group_name = kwargs.get('log_group_name')
        self.log_stream_prefix = kwargs.get('log_stream_prefix')
        self.filter_pattern = kwargs.get('filter_pattern')
        self.watch = kwargs.get('watch')
        self.color_enabled = kwargs.get('color_enabled')
        self.output_stream_enabled = kwargs.get('output_stream_enabled')
        self.output_group_enabled = kwargs.get('output_group_enabled')
        self.output_timestamp_enabled = kwargs.get('output_timestamp_enabled')
        self.output_ingestion_time_enabled = kwargs.get(
            'output_ingestion_time_enabled')
        self.start = self.parse_datetime(kwargs.get('start'))
        self.end = self.parse_datetime(kwargs.get('end'))
        self.query = kwargs.get('query')
        if self.query is not None:
            self.query_expression = jmespath.compile(self.query)
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

        max_stream_length = max([len(s) for s in streams]) if streams else 10 # TODO add warning message here
        group_length = len(self.log_group_name)

        # Note: filter_log_events paginator is broken
        # ! Error during pagination: The same next token was received twice
        do_wait = object()

        def generator():
            """Yield events into trying to deduplicate them using a lru queue.
            AWS API stands for the interleaved parameter that:
                interleaved (boolean) -- If provided, the API will make a best
                effort to provide responses that contain events from multiple
                log streams within the log group interleaved in a single
                response. That makes some responses return some subsequent
                response duplicate events. In a similar way when awslogs is
                called with --watch option, we need to findout which events we
                have alredy put in the queue in order to not do it several
                times while waiting for new ones and reusing the same
                next_token. The site of this queue is MAX_EVENTS_PER_CALL in
                order to not exhaust the memory.
            """
            interleaving_sanity = deque(maxlen=self.MAX_EVENTS_PER_CALL)
            kwargs = {'logGroupName': self.log_group_name,
                      'interleaved': True}

            if streams:
                kwargs['logStreamNames'] = streams

            if self.start:
                kwargs['startTime'] = self.start

            if self.end:
                kwargs['endTime'] = self.end

            if self.filter_pattern:
                kwargs['filterPattern'] = self.filter_pattern

            while True:
                # print 'filtering log events with dictionary: {}'.format(kwargs)
                response = self.client.filter_log_events(**kwargs)

                for event in response.get('events', []):
                    if event['eventId'] not in interleaving_sanity:
                        interleaving_sanity.append(event['eventId'])
                        yield event

                if 'nextToken' in response:
                    kwargs['nextToken'] = response['nextToken']
                else:
                    yield do_wait

        def consumer():
            for event in generator():

                if event is do_wait:
                    if self.watch:
                        time.sleep(1)
                        continue
                    else:
                        return

                output = []
                if self.output_group_enabled:
                    output.append(
                        self.color(
                            self.log_group_name.ljust(group_length, ' '),
                            'green'
                        )
                    )
                if self.output_stream_enabled:
                    output.append(
                        self.color(
                            event['logStreamName'].ljust(max_stream_length,
                                                         ' '),
                            'cyan'
                        )
                    )
                if self.output_timestamp_enabled:
                    output.append(
                        self.color(
                            milis2iso(event['timestamp']),
                            'yellow'
                        )
                    )
                if self.output_ingestion_time_enabled:
                    output.append(
                        self.color(
                            milis2iso(event['ingestionTime']),
                            'blue'
                        )
                    )

                message = event['message']
                if self.query is not None and message[0] == '{':
                    parsed = json.loads(event['message'])
                    message = self.query_expression.search(parsed)
                    if not isinstance(message, six.string_types):
                        message = json.dumps(message)
                output.append(message.rstrip())

                print(' '.join(output))
                try:
                    sys.stdout.flush()
                except IOError as e:
                    if e.errno == errno.EPIPE:
                        # SIGPIPE received, so exit
                        os._exit(0)
                    else:
                        # We don't want to handle any other errors from this
                        raise
        try:
            consumer()
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

    def color(self, text, color):
        """Returns coloured version of ``text`` if ``color_enabled``."""
        if self.color_enabled:
            return colored(text, color)
        return text

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
