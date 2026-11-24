"""Однозначный JSON на границе Python/1С."""
import json
import math


def unique_object(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('Duplicate JSON member')
        value[key]=item
    return value


def invalid_constant(value):
    raise ValueError('Non-finite JSON number')


def strict_json(raw):
    if isinstance(raw,bytes):raw=raw.decode('utf-8-sig')
    try:
        result=json.loads(raw,object_pairs_hook=unique_object,parse_constant=invalid_constant)
        stack=[(result,0)];count=0
        while stack:
            value,depth=stack.pop();count+=1
            if depth>64 or count>100000:raise ValueError('JSON structure exceeds limit')
            if isinstance(value,float) and not math.isfinite(value):raise ValueError('Non-finite JSON number')
            if isinstance(value,dict):stack.extend((item,depth+1) for item in value.values())
            elif isinstance(value,list):stack.extend((item,depth+1) for item in value)
        return result
    except RecursionError:
        raise ValueError('JSON is too deeply nested') from None
