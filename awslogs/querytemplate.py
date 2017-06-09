import yaml
import pystache

class QueryTemplate(object):

    """
    template_args = {}
    for arg in self.query_template_args:
        key_val = arg.split('=', 1)
        if len(key_val) != 2:
            raise Exception('Invalid arg: {}'.format(arg)) # TODO move arg validation and parsing to bin
        template_args[key_val[0]] = key_val[1] # todo figure out a more idiomatidc way to do this



    query_template = yaml.load(self.query_template_file) # TODO validate query template
    for k, v in query_template.items():
        query_template[k] = pystache.render(v, template_args)
    """


    def __init__(self,
                 query_template_file,
                 *template_args):
        print 'template args {}'.format(*template_args)

        processed_query = self.__populate_query_template(query_template_file, *template_args)

        print 'got processed_query: {}'.format(processed_query)


        self.log_group_name = self.__validate_arg(processed_query, 'log_group_name')
        self.log_stream_prefix = self.__validate_arg(processed_query, 'log_stream_prefix')
        self.filter_pattern = processed_query.get('aws_filter_pattern')
        self.output_format = processed_query.get('output_format')



    def __validate_arg(self, arg_dict, arg_name):
        arg = arg_dict.get(arg_name)
        if not arg:
            raise ValueError('{} required in template!'.format())
        return arg



    def __populate_query_template(self, query_template_file, template_args):
        # TODO find a more idiomatic way to do this
        print 'printing some shit'
        print 'got file: {}'.format(query_template_file)
        print 'got args: {}'.format(template_args)
        template_args_dict = {}
        for arg in template_args:
            print 'got arg: {}'.format(arg)
            key_val = arg.split('=', 1)
            if len(key_val) != 2:
                raise ValueError('Invalid template arg: {}'.format(arg))
            template_args_dict[key_val[0]] = key_val[1] # todo figure out a more idiomatidc way to do this

        query_template = yaml.load(query_template_file)
        for k, v in query_template.items():
            query_template[k] = pystache.render(v, template_args_dict)

        return query_template
