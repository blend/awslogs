import sys
import jmespath
from termcolor import colored
from datetime import datetime
from botocore.compat import json, six

def milis2iso(milis):
    res = datetime.utcfromtimestamp(milis/1000.0).isoformat()
    return (res + ".000")[:23] + 'Z'

class LogPrinter(object):

    def __init__(self, log_group_name, max_stream_length, **kwargs):
        self.log_group_name = log_group_name
        self.max_stream_length = max_stream_length
        self.color_enabled = kwargs.get('color_enabled')
        self.output_stream_enabled = kwargs.get('output_stream_enabled')
        self.output_group_enabled = kwargs.get('output_group_enabled')
        self.output_timestamp_enabled = kwargs.get('output_timestamp_enabled')
        self.output_ingestion_time_enabled = kwargs.get('output_ingestion_time_enabled')
        self.query = kwargs.get('query')
        if self.query:
            self.query_expression = jmespath.compile(self.query)


    def print_log(self, event):
        output = []
        group_length = len(self.log_group_name)
        if self.output_group_enabled:
            output.append(
                self.__color(
                    self.log_group_name.ljust(group_length, ' '),
                    'green'
                )
            )
        if self.output_stream_enabled:
            output.append(
                self.__color(
                    event['logStreamName'].ljust(self.max_stream_length,
                                                 ' '),
                    'cyan'
                )
            )
        if self.output_timestamp_enabled:
            output.append(
                self.__color(
                    milis2iso(event['timestamp']),
                    'yellow'
                )
            )
        if self.output_ingestion_time_enabled:
            output.append(
                self.__color(
                    milis2iso(event['ingestionTime']),
                    'blue'
                )
            )

        message = event['message']
        # TODO add this back in
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

    def __color(self, text, color):
        """Returns coloured version of ``text`` if ``color_enabled``."""
        if self.color_enabled:
            return colored(text, color)
        return text
