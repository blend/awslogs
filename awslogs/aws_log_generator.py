import sys
from collections import deque


MAX_EVENTS_PER_CALL = 10000

END_OF_STREAM = object()

# TODO look into renaming this class / file to conform to standard naming conventions


class AWSLogGenerator(object):

    MAX_EVENTS_PER_CALL = 10000

    END_OF_STREAM = object()

    # TODO figure out a better way to initialize this object
    def __init__(self,
                 watch=False,
                 log_group_name=None,
                 log_streams=None,
                 filter_pattern=None,
                 start_time='1w',
                 end_time=None):
        self.watch = watch
        self.log_group_name = log_group_name
        self.log_streams = log_streams
        self.start_time = start_time
        self.filter_pattern = filter_pattern
        self.end_time = end_time # do something with this argument

        # TODO do some validation here



    def __generate_logs(self, client): # move client argument to member variable

        interleaving_sanity = deque(maxlen=self.MAX_EVENTS_PER_CALL)

        kwargs = {'logGroupName': self.log_group_name,
                  'logStreamNames': self.log_streams,
                  'startTime': self.start_time}

        if self.filter_pattern:
            kwargs['filterPattern'] = self.filter_pattern

        while True:
            # print 'filtering log events with dictionary: {}'.format(kwargs)
            response = client.filter_log_events(**kwargs)

            for event in response.get('events', []):
                if event['eventId'] not in interleaving_sanity:
                    interleaving_sanity.append(event['eventId'])
                    yield event

            if 'nextToken' in response:
                kwargs['nextToken'] = response['nextToken']
            else:
                yield END_OF_STREAM


    def get_and_print_logs(self, client, log_printer):
        for event in self.__generate_logs(client):
            if event is END_OF_STREAM:
                sys.stderr.write('got event: {}'.format(event))
                if self.watch:
                    time.sleep(1)
                    continue
                else:
                    return

            log_printer.print_log(event)
