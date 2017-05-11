import os
import string
import sys

from logger import Logger
import api_converter


__usage_string = """
    python script.py SRC DST

Where:
    SRC: path to a text file containing list of APIs in JNI format
    DST: path where the output XML will be created (with file name)
"""


def __ignore_line(line):
    return (len(line) < 1) or \
           (line.startswith("!API23")) or \
           (line == "# ------")


def __process_comment(line, prev_line, next_line):
    if prev_line.startswith("#"):
        start = ""
    else:
        start = "<!--"

    if next_line.startswith("#"):
        end = ""
    else:
        end = "-->"
    return '%s %s %s' % (start, line.replace('#', ''), end)


def __to_valid_xml_name(name):
    return name.replace("<", "&lt;").replace(">", "&gt;")


def __create_api_tag(api):
    class_name = "<class>%s</class>" % api.object_class
    method_name = "<method>%s</method>" % __to_valid_xml_name(api.method_name)
    method_params = "<params>\n"

    for param in api.params_list:
        method_params += "\t\t\t<param>%s</param>\n" % param

    method_params += "\t\t</params>"
    return_type = "<return>%s</return>" % api.return_class
    is_static = "<static>%s</static>" % api.is_static
    jni = "<jni>%s</jni>" % __to_valid_xml_name(api.jni_signature)
    version = "<version>All</version>"

    api_tag = """
        <api>
           %s
           %s
           %s
           %s
           %s
           %s
           %s
        </api>""" % (class_name, method_name, method_params, return_type, is_static, jni, version)

    return api_tag


def __create_signature_params(params_list):
    param_str = ""
    for idx, param in enumerate(params_list):
        param_str += "%s p%d, " % (param, idx)

    # Remove end if necessary
    if param_str.endswith(", "):
        param_str = param_str[:-2]

    return param_str


def __create_log_params(signature_params):
    # java.lang.String "+convert(p0)+" boolean "+convert(p1)+" boolean "+convert(p2)+" boolean "+convert(p3)+"
    params_log = signature_params \
        .replace(", ", ')+"') \
        .replace(" ", '"+convert(') \
        .replace('"+', ' "+') \
        .replace('+"', '+" ')

    if len(params_log) > 0:
        params_log += ')+"'

    return params_log


def __create_invoke_params(params_list):
    params_invoke = ""

    for idx, param in enumerate(params_list):
        params_invoke += ", p%d" % idx

    return params_invoke


def __create_dynamic_part(api):
    invoke_params = __create_invoke_params(api.params_list)

    # has return
    if api.return_class != "void":
        return_statement = "return"
        return_cast = "(%s)" % api_converter.degenerify(api.return_class)
        return_var = "returnVal"
        attrib_statement = "Object returnVal = "
    else:
        return_statement = ""
        return_cast = ""
        return_var = "null"
        attrib_statement = ""

    if api.is_static:
        invoke = "invokeStatic"
        invoke_params = invoke_params[2:]
    else:
        invoke = "invoke"
        invoke_params = "_this" + invoke_params

    dynamic_template = string.Template("""
        $ASTATEMENT OriginalMethod.by(new $DOLAR() {}).$INVOKE ($PARAMS_INVOKE);
        $RSTATEMENT $RETURN_CAST monitorHook.hookAfterApiCall(logSignature, $RETURN_CAST $RETURN_VAR);
    """)
    dynamic_part = dynamic_template.substitute(
        {"RSTATEMENT": return_statement,
         "PARAMS_INVOKE": invoke_params,
         "RETURN_VAR": return_var,
         "RETURN_CAST": return_cast,
         "DOLAR": "$",
         "ASTATEMENT": attrib_statement,
         "INVOKE": invoke
         })

    return dynamic_part


def __create_name_id(api, seq):
    if "<" in api.method_name:
        name_method_name = "_ctor"
    else:
        name_method_name = __to_valid_xml_name(api.method_name)

    name_object_class = api.object_class.replace(".", "_")
    name_method_name = name_method_name.replace(".", "_")

    params = __create_signature_params(api.params_list)

    if len(params) > 0:
        params = ", " + params

    if api.is_static:
        params = params[2:]
    else:
        params = "Object _this " + params

    return "redir_%s_%s_%d(%s)" % (name_object_class, name_method_name, seq, params)


def __create_log_signature(api):
    signature_params = __create_signature_params(api.params_list)
    log_params = __create_log_params(signature_params)

    sign_template = string.Template(
        """ "TId: "+threadId+" objCls: $CLASS mthd: $METHOD retCls: $RETURN params: $PARAMS stacktrace: "+stackTrace""")
    sign = sign_template.substitute({
        "CLASS": api.object_class,
        "METHOD": __to_valid_xml_name(api.method_name),
        "RETURN": api.return_class,
        "PARAMS": log_params
    })

    return sign


def __create_code_tag(api):
    dynamic_part = __create_dynamic_part(api)
    dynamic_tag = "<invoke>\n%s\n</invoke>" % dynamic_part

    return dynamic_tag


def __process_non_comment(seq, line):
    # only API 23 reach this point
    jni_signatue = line.replace("!API19 ", "")
    # print(jni_signatue)

    api = api_converter.from_descriptor(jni_signatue)
    api_tag = __create_api_tag(api)

    policty_tag = "<policy>Allow</policy>"

    hook_id = "%s->%s" % (api.object_class, __to_valid_xml_name(api.method_name))
    hook_tag = "<hook>%s</hook>" % hook_id

    ctor_tag = "<name>%s</name>" % __create_name_id(api, seq)
    code_tag = __create_code_tag(api)

    log_signature_tag = "<logId>%s</logId>" % __create_log_signature(api)

    dst_line = """
<apiPolicy>
%s <!-- API -->
%s <!-- POLICY -->
%s <!-- HOOK ID -->
%s <!-- METHOD ID -->
%s <!-- LOG SIGNATURE -->
%s <!-- INVOKE_CODE -->
</apiPolicy>""" % (api_tag,
                   policty_tag,
                   hook_tag,
                   ctor_tag,
                   log_signature_tag,
                   code_tag)

    return dst_line


def process_file(src, dst):
    data = ['<?xml version="1.0"?>', "<policies_list>"]

    f = open(src, 'r')
    src_data = f.readlines()
    f.close()

    src_data = [x.strip() for x in src_data]

    for seq, src_line in enumerate(src_data):
        if seq > 0:
            prev_line = src_data[seq - 1]
        else:
            prev_line = ""

        if seq < len(src_data) - 1:
            next_line = src_data[seq + 1]
        else:
            next_line = ""

        # Just white space or single comment
        if __ignore_line(src_line):
            continue

        # Just comment
        if src_line.startswith('#'):
            dst_line = __process_comment(src_line, prev_line, next_line)
        # Valid API, create config
        else:
            dst_line = __process_non_comment(seq, src_line)

        data.append(dst_line)

    data.append("</policies_list>")

    f = open(dst, 'w')

    for l in data:
        f.write("%s\n" % l)

    f.close()

    return data


def __invalid_params():
    return len(sys.argv) < 2 or \
           not os.path.exists(sys.argv[1])


if __name__ == "__main__":
    if __invalid_params():
        print(__usage_string)
    else:
        # Create new file
        src_file = sys.argv[1]
        dst_file = sys.argv[2]
        dst_data = process_file(src_file, dst_file)

        logger = Logger("api_converter_script").get()

        logger.info("Script started")
        logger.info("Source file: %s", src_file)
        logger.info("Destination file: %s", dst_file)

        # Create second copy of the file in the local directory for easier cehcking
        dst_file = os.path.join(".", 'monitored_apis.xml')
        process_file(src_file, dst_file)

        logger.info("Done")
