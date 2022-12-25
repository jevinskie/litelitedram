from collections import abc

from migen.fhdl.module import Module
from migen.fhdl.structure import Signal
from migen.genlib.record import Record


def is_attr_builtin(attr_name):
    return attr_name[:2] == "__" and attr_name[-2:] == "__"


# fmt: off
def is_builtin_type(obj):
    return isinstance(obj, (bool, bytearray, bytes, complex, dict, float, int,
                            list, range, set, str, tuple, type, memoryview, type(None)))
# fmt: on


def is_builtin_scalar(obj):
    return isinstance(obj, (bool, complex, float, int, type))


def is_raw_sequence(obj):
    return isinstance(obj, (bytearray, bytes, range, str, memoryview))


def non_builtin_attrs(obj):
    return [a for a in dir(obj) if not is_attr_builtin(a)]


def get_signals(obj, recurse=False, stack=None):
    if stack is None:
        stack = set()
    if id(obj) in stack:
        return set()
    if is_builtin_scalar(obj) or is_raw_sequence(obj):
        return set()
    signals = set()
    for attr_name in dir(obj):
        if is_attr_builtin(attr_name):
            continue
        attr = getattr(obj, attr_name)
        if isinstance(attr, Signal):
            signals.add(attr)
        elif isinstance(attr, Record):
            print(f"record: {migen_obj_name(attr)} layout:")
            print(attr.layout)
            assert False
            for robj in attr.flatten():
                signals.add(robj)
        elif recurse:
            if isinstance(attr, abc.Mapping):
                for v in attr.values():
                    signals |= get_signals(v, recurse=True, stack=stack | set([id(obj), id(attr)]))
            elif isinstance(attr, abc.Sequence):
                for v in attr:
                    signals |= get_signals(v, recurse=True, stack=stack | set([id(obj), id(attr)]))
            else:
                signals |= get_signals(attr, recurse=True, stack=stack | set([id(obj), id(attr)]))
    return signals


def get_signals_tree(obj, stack=None):
    if stack is None:
        stack = set()
    if id(obj) in stack:
        return {}
    if is_builtin_scalar(obj) or is_raw_sequence(obj):
        return {}
    signals = {}
    to_inspect = {}
    for attr_name in dir(obj):
        to_inspect[attr_name] = getattr(obj, attr_name)
    for attr_name in dir(obj):
        if is_attr_builtin(attr_name):
            continue
        attr = getattr(obj, attr_name)
        key = f"{attr_name}"
        if isinstance(attr, Signal):
            signals[key] = attr
        elif isinstance(attr, Record):
            for sig_tup in attr.layout:
                name = sig_tup[0]
                sub_signal = getattr(attr, name)
                signals[f"{key}.{name}"] = sub_signal
        elif isinstance(obj, Module) and attr_name == "_submodules":
            for i, sm in enumerate(attr):
                name = f"sm_{type(sm[1]).__name__}_{i}" if sm[0] is None else sm[0]
                sub_signals = get_signals_tree(sm[1], stack=stack | set([id(obj), id(attr)]))
                if len(sub_signals):
                    signals[f"submodules.{name}"] = sub_signals
        if isinstance(attr, abc.Mapping):
            for k, v in attr.items():
                subkey = f"{key}.{k}"
                sub_signals = get_signals_tree(v, stack=stack | set([id(obj), id(attr)]))
                if len(sub_signals):
                    signals[subkey] = sub_signals
        elif isinstance(attr, abc.Sequence):
            sub_signals = []
            for v in attr:
                subsigs = get_signals_tree(v, stack=stack | set([id(obj), id(attr)]))
                if len(subsigs):
                    sub_signals.append(subsigs)
            if len(sub_signals):
                signals[key] = sub_signals
        else:
            sub_signals = get_signals_tree(attr, stack=stack | set([id(obj), id(attr)]))
            if len(sub_signals):
                signals[key] = sub_signals
    return signals


def migen_obj_name(obj):
    return obj.backtrace[-1][0]


def rename_migen_obj(obj, name):
    obj.backtrace.append((name, None))


def rename_migen_fsm(fsm, name):
    rename_migen_obj(fsm.state, f"{name}_state")
    rename_migen_obj(fsm.next_state, f"{name}_next_state")
