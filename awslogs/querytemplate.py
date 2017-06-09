import yaml
import pystache
from . import exceptions

class QueryTemplate(object):

    def __init__(self,
                 query_template_file,
                 *template_args):

        processed_query = self.__populate_query_template(query_template_file, *template_args)

        self.log_group_name = self.__validate_arg(processed_query, 'log_group_name')
        self.log_stream_prefix = self.__validate_arg(processed_query, 'log_stream_prefix')
        self.filter_pattern = processed_query.get('filter_pattern')
        self.output_format = processed_query.get('query')



    def __validate_arg(self, arg_dict, arg_name):
        arg = arg_dict.get(arg_name)
        if not arg:
            raise exceptions.InvalidQueryArgumentError(arg_name)
        return arg


    def __populate_query_template(self, query_template_file, template_args):
        # TODO find a more idiomatic way to do this
        template_args_dict = {}
        if template_args:
            for arg in template_args:
                key_val = arg.split('=', 1)
                if len(key_val) != 2:
                    raise exceptions.InvalidQueryArgument(arg)
                template_args_dict[key_val[0]] = key_val[1] # todo figure out a more idiomatidc way to do this

        query_template = yaml.load(query_template_file)
        if not query_template:
            raise exceptions.AWSLogsException("Empty or invalid query template file.")
        for k, v in query_template.items():
            renderer = pystache.Renderer(missing_tags='strict')
            try:
                query_template[k] = renderer.render(v, template_args_dict)
            except pystache.context.KeyNotFoundError as e:
                raise exceptions.MissingTemplateArgumentError(e.key)

        return query_template
