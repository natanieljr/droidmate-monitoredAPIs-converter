import os
import string
import sys
import json

from logger import Logger
import api_converter


__usage_string = """
    python script.py SRC DST

Where:
    SRC: path to a text file containing list of APIs in JNI format
    DST: path where the output JSON file will be created (with file name)
"""


def __ignore_line(line):
    return (len(line) < 1) or \
           (line.startswith("!API23")) or \
           (line == "# ------")


def __create_api_dict(api):
    api_dict = {"className":        api.object_class,
                "methodName":       api.method_name,
                "paramList":        api.params_list,
                "returnType":       api.return_class,
                "isStatic":         api.is_static,
                "jniSignature":     api.jni_signature,
                "platformVersion":  "All",
                }

    return api_dict


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
        name_method_name = api.method_name

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
        "METHOD": api.method_name,
        "RETURN": api.return_class,
        "PARAMS": log_params
    })

    return sign


def __create_code_dict(api):
    dynamic_part = __create_dynamic_part(api)

    return {"invokeAPICode": dynamic_part,
            "defaultReturnValue": __get_default__return(api),
            "logID": __create_log_signature(api),
            "customPolicyConstraint": ""
            }


def __get_default__return(api):
    if api.return_class == "byte":
        return "0"
    elif api.return_class == "char":
        return "'A'"
    elif api.return_class == "double":
        return "0"
    elif api.return_class == "float":
        return "0"
    elif api.return_class == "int":
        return "0"
    elif api.return_class == "long":
        return "0"
    elif api.return_class == "short":
        return "0"
    elif api.return_class == "boolean":
        return "false"
    elif api.return_class == "void":
        return ""
    #for objects
    else:
        return "null"


def __process_non_comment(seq, line):
    # only API 23 reach this point
    jni_signatue = line.replace("!API19 ", "")
    # print(jni_signatue)

    api = api_converter.from_descriptor(jni_signatue)
    api_dict = __create_api_dict(api)
    code_dict = __create_code_dict(api)

    other_dict = {"policy": "Allow",
                  "hookedMethod": "%s->%s" % (api.object_class, api.method_name),
                  "signature": __create_name_id(api, seq)
                  }

    dst_dict = {}
    dst_dict.update(api_dict)
    dst_dict.update(code_dict)
    dst_dict.update(other_dict)

    return dst_dict


def process_file(src, dst):
    data = []

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

        # Ignored comments, Valid APIs, create config
        if not src_line.startswith('#'):
            dst_dict = __process_non_comment(seq, src_line)
            data.append(dst_dict)

    new_api_file = {"apis" : data}

    json.dumps(new_api_file)

    f = open(dst, 'w')
    json.dump(new_api_file, f)
    f.close()

    return data


def __invalid_params():
    return len(sys.argv) < 2 or \
           not os.path.exists(sys.argv[1])


class JSONObject:
    def __init__(self, d):
        self.__dict__ = d

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
        dst_file = os.path.join(".", 'monitored_apis.json')
        process_file(src_file, dst_file)

        logger.info("Done")
