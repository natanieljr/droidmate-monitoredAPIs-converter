class Api(object):
    object_class = ""
    method_name = ""
    params_list = []
    return_class = ""
    is_static = False
    jni_signature = ""


__source_to_base_type_map = {
    "byte": "B",
    "char": "C",
    "double": "D",
    "float": "F",
    "int": "I",
    "long": "J",
    "short": "S",
    "boolean": "Z",
    "void": "V"
}

__base_to_source_type_map = {
    "B": "byte",
    "C": "char",
    "D": "double",
    "F": "float",
    "I": "int",
    "J": "long",
    "S": "short",
    "Z": "boolean",
    "V": "void"
}

__source_to_object_type_map = {
    "byte": "Byte",
    "char": "Character",
    "double": "Double",
    "float": "Float",
    "int": "Integer",
    "long": "Long",
    "short": "Short",
    "boolean": "Boolean"
}


def degenerify(return_class):
    # // Generic types contain space in their name, e.g. "<T> T".
    if " " in return_class:
        i = 0
        while return_class[1] != ' ':
            i += 1
        degenerified = return_class[i:]  # Will return only "T" in the above - given example.
    else:
        degenerified = return_class  # No generics, return type as- is.

    # This conversion is necessary to avoid error of kind
    # "error: incompatible types: Object cannot be converted to boolean"
    if degenerified in __source_to_object_type_map:
        degenerified = __source_to_object_type_map[degenerified]

    return degenerified


def __jni_to_source_code(type, replace_dollars_with_dots=False):
    out = ""
    arrays_count = type.count("[")

    type_prim = type.replace("[", "")

    if type_prim.startswith("L"):
        assert type_prim.endswith(";")
        type_prim = type_prim[1:-1].replace("/", ".")

        if replace_dollars_with_dots:
            type_prim = type_prim.replace("\$", ".")

        out += type_prim
    else:
        if type_prim.endswith(";"):
            type_prim = type_prim[:-1]

        assert len(type_prim) == 1
        base_type = filter(lambda x: __base_to_source_type_map.has_key(x), type_prim)
        assert len(base_type) > 0
        out += __base_to_source_type_map[base_type]

    out += "[]" * arrays_count
    return out


def __match_class_field_descriptors(class_field_descriptors):
    # Notation reference: http://docs.oracle.com/javase/specs/jvms/se7/html/jvms-4.html#jvms-4.3.2
    # (?: is a non-capturing group. See http://docs.oracle.com/javase/7/docs/api/java/util/regex/Pattern.html#special
    input_data = class_field_descriptors

    out = []
    while len(input_data) > 0:
        if input_data[0] in __base_to_source_type_map:
            source_param = __base_to_source_type_map[input_data[0]]
            start_pos = 1
        else:
            jni_param = input_data.split(";")[0] + ";"
            source_param = __jni_to_source_code(jni_param)
            start_pos = len(jni_param)

        input_data = input_data[start_pos:]
        out.append(source_param.replace("$", "."))

    return out


def from_descriptor(descriptor):
    #print(descriptor)
    object_class = descriptor.split("->")[0]
    object_class = __jni_to_source_code(object_class)  # e.g. android.content.ContentProviderClient

    if " " in descriptor:
        method_header, staticness = descriptor.split(" ")
    else:
        method_header = descriptor
        staticness = ""

    assert staticness in ["static", "instance", ""]
    is_static = staticness == "static"

    """ This line ensures that if there are no params, the match below will match a one-space string to methodParams,
       instead of skipping it and matching returnClass to methodParams.
       The ApiLogcatMessage.matchClassFieldDescriptors then will properly handle the " " methodParams."""

    method_header = method_header.replace("()", "( )")
    # methodName: e.g. update
    # returnClass: e.g. Ljava/lang/Object;
    method_name = method_header.split("(")[0]
    method_params = method_header.split("(")[1].split(")")[0]
    return_class = method_header.split("(")[1].split(")")[1]

    method_name = method_name.split("->")[1]

    if method_params == " ":
        method_params = ""

    params_list = __match_class_field_descriptors(method_params)
    return_class = __jni_to_source_code(return_class)

    api = Api()
    api.object_class = object_class
    api.method_name = method_name
    api.params_list = params_list
    api.return_class = return_class
    api.is_static = is_static
    api.jni_signature = descriptor

    print "%s->%s(%s)" % (object_class, method_name, str(params_list).replace("[", "").replace("]", "").replace("'", "").replace(" ", ""))

    return api
