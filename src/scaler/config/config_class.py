import argparse
import dataclasses
import enum
import os
import sys
import typing
from typing import Any, Dict, List, Optional, Type, TypeVar

from scaler.config.mixins import ConfigType

T = TypeVar("T", bound="ConfigClass")


class ConfigClass:
    """
    An abstract interface for dataclasses where the fields define command line options,
    config file options, and environment variables.

    Subclasses of `ConfigClass` must be dataclasses.
    Subclasses of `ConfigClass` are called "config classes".

    ## Config Files

    All options with a long name can be parsed from a TOML config file specified with `--config` or `-c`.
    The section name is determined by the subclass' implementation of `.section_name()`.

    Keys in the config file correspond to the long name of the argument
    and may use underscores or hyphens interchangeably.

    For example, given the config class:
    ```python
    @dataclasses.dataclass
    class MyConfig(ConfigClass):
        my_field: int = 5
    ```

    Both of the following config files are valid:
    ```
    [my_section]
    my_field = 10
    ```

    ```
    [my_section]
    my-field = 10
    ```

    ## Environment Variables

    Any parameter can be configured to read from an environment variable by adding `env_var="NAME"` to the field
    metadata.

    ```python
    # can be set as --my-field on the command line or in a config file, or using the environment variable `NAME`
    my_field: int = dataclasses.field(metadata=dict(env_var="NAME"))
    ```

    ## Precedence

    When a parameter is supplied in multiple ways, the following precedence is observed:
    command line > environment variables > config file > defaults

    ## Customization

    Any key values included in the field's metadata will be passed through to `.add_argument()`
    and will always take precedence over derived values, except for `default`.

    The value for `default` is taken from the field's default. Providing `default` in the field
    metadata will result in a `TypeError`.

    ```python
    # passes through options
    custom_field: int = dataclasses.field(
        metadata=dict(
            choices=["apples", "oranges"],
            help="choose a fruit",
        )
    )

    # TypeError!
    bad: int = dataclasses.field(metadata=dict(default=0))
    ```

    ## Naming Fields

    The name of the dataclass fields (replacing underscores with hyphens) is used
    as the long option name for command line and config file parameters.
    A short name for the argument can be provided in the field metadata using the `short` key.
    The value is the short option name and must include the hyphen, e.g. `-n`.

    There is one restriction: `--config` and `-c` are reserved for the config file.

    ```python
    # this will have long name --field-one, and no short name
    field_one: int = 5

    # sets a short name
    field_two: int = dataclasses.field(default=5, metadata=dict(short="-f2"))
    ```

    ## Default Values

    The default value of the field is also used as the default for the argument parser.

    ```python
    lang: str = "en"
    name: str = dataclasses.field(default="Arthur")
    ```

    ## Positional Parameters

    You can set `positional=True` in the metadata dict to make an argument positional.
    In this case long and short names are ignored, use `name` to override the name of the option.
    The position is dependent on field ordering.

    ```python
    # both of these are positional, and field one must be specified before field two
    field_one: int = dataclasses.field(metadata=dict(positional=True))
    field_two: int = dataclasses.field(metadata=dict(positional=True))
    ```

    ## Sub-commands

    A field with `subcommand="<toml_section>"` in its metadata declares a sub-command:
    - **Field name** -> CLI sub-command name
    - **`subcommand` value** -> TOML section to read when this sub-command is active
    - **Field type** -> `Optional[SomeConfigClass]` with `default=None`

    ## Section Fields

    A field with `section="<toml_section>"` in its metadata is populated from the TOML file only
    (no CLI argument). The field type may be `Optional[SomeConfigClass]` or `List[SomeConfigClass]`.

    ## Composition

    Config classes can be composed. If a config class has fields that are config classes,
    then the options of the child config class are inherited as if that child config class'
    fields were added to the parent, for the purpose of parsing arguments. When the dataclass
    is created, the structure is kept.

    Care needs to be taken so that field names do not conflict with each other.
    The name of fields in nested config classes are in the same namespace as those
    in the parent and other nested config classes.

    ## Enums

    Enums are parsed by their name, for instance the enum:

    ```python
    class Color(Enum):
        RED = "red"
        GREEN = "green"
        BLUE = "blue"
    ```

    Will accept "RED", "GREEN", and "BLUE" as arguments on the command line.
    As usual this can be overriden by explicitly setting the `type` field.

    ## Parameter Types

    The type of a field is used as the type in argument parsing, meaning that it must be able
    to be directly constructed from a string.

    Special handling is implemented for several common types:
    - `bool`: parses from "true" and "false", and all upper/lower case variants
    - subclasses of `ConfigType`: uses the `.from_string()` method
    - `Optional[T]`, `T | None`: parsed as `T` and sets `required=False`
    - `List[T]`, `list[T]`: parsed as `T`, and sets `nargs="*"`
    - sublcasses of `enum.Enum`: values are parsed by name

    For generic types, the `T` is parsed recursively following the rules here.
    For example, `Optional[T]` where `T` is a subclass of `ConfigType`
    will still use `T.from_string()`.

    as usual, all of these can be overriden by setting the option in the metadata.

    ```python
    # this provides a custom `type` to parse the input as hexadecimal
    # `type` must be a callable that accepts a string
    # refer to the argparse docs for more
    hex: int = dataclasses.field(metadata=dict(type=lambda s: int(s, 16)))

    class MyConfigType(ConfigType):
        ...

    # this will work as expected
    my_field: MyConfigType

    # this requires special handling
    tuples: Tuple[int, ...] = dataclasses.field(metadata=dict(type=int, nargs="*"))

    # works automatically, defaults to `nargs="*"`
    integers: List[int]

    # ... but we can override that
    integers2: List[int] = dataclasses.field(metadata=dict(nargs="+"))

    # this will automatically have `required=False` set
    maybe: Optional[str]
    """

    @classmethod
    def configure_parser(cls: type, parser: argparse.ArgumentParser) -> None:
        for field in dataclasses.fields(cls):  # type: ignore[arg-type]
            if "subcommand" in field.metadata or "section" in field.metadata:
                continue  # handled by parse()

            if is_config_class(field.type):
                field.type.configure_parser(parser)  # type: ignore[union-attr]
                continue

            # Strip keys that argparse doesn't understand
            kwargs = {
                k: v
                for k, v in field.metadata.items()
                if k not in ("env_var", "positional", "long", "short", "name", "subcommand", "section")
            }

            if field.metadata.get("positional", False):
                args = [field.metadata.get("name", field.name)]
            else:
                long_name = field.metadata.get("long", f"--{field.name.replace('_', '-')}")
                args = [long_name, field.metadata["short"]] if "short" in field.metadata else [long_name]
                kwargs["dest"] = field.name

            if "default" in kwargs:
                raise TypeError("'default' cannot be provided in field metadata")

            if field.default is not dataclasses.MISSING:
                kwargs["default"] = field.default

            if field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                kwargs["default"] = field.default_factory()

            # when store_true or store_false is set, setting the type raises a type error
            if kwargs.get("action") not in ("store_true", "store_false"):
                # sometimes the user will set the type manually
                if "type" not in kwargs:
                    for key, value in get_type_args(field.type).items():
                        if key not in kwargs:
                            kwargs[key] = value

            parser.add_argument(*args, **kwargs)

    @classmethod
    def parse(cls: Type[T], program_name: str, section: str) -> T:
        subcommand_fields = [
            field for field in dataclasses.fields(cls) if "subcommand" in field.metadata  # type: ignore[arg-type]
        ]

        if subcommand_fields:
            # Root parser: routes to sub-commands.
            parser = argparse.ArgumentParser(prog=program_name, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
            parser.add_argument("--config", "-c", metavar="FILE", help="Path to the TOML configuration file.")

            # Pre-scan for --config before building the subparser tree so TOML
            # defaults can be injected into each subparser during construction.
            config_path = _find_config_arg(sys.argv)
            toml_data = _load_toml(config_path) if config_path else {}

            _build_subparser_tree(cls, parser, parent_cls=cls, sections=[section], dest="_sub", toml_data=toml_data)

            kwargs = vars(parser.parse_args())
            kwargs.pop("config", None)

            return _reconstruct_recursive(cls, kwargs, dest="_sub")

        # Normal path.
        parser = argparse.ArgumentParser(prog=program_name, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        parser.add_argument("--config", "-c", metavar="FILE", help="Path to the TOML configuration file.")
        cls.configure_parser(parser)

        # Pass 1: locate --config without failing on unrecognised args.
        config_path_str: Optional[str] = vars(parser.parse_known_args()[0]).get("config")

        # Load TOML and inject section values as defaults (below CLI, above hardcoded).
        toml_data: Dict[str, Any] = {}  # type: ignore[no-redef]
        if config_path_str:
            toml_data = _load_toml(config_path_str)
            toml_defs = _toml_section_defaults(toml_data.get(section, {}), cls)
            if toml_defs:
                parser.set_defaults(**toml_defs)

        # Env-var defaults override TOML but are overridden by CLI.
        env_defs = _env_defaults(cls)
        if env_defs:
            parser.set_defaults(**env_defs)

        # Pass 2: full parse — CLI wins.
        kwargs = vars(parser.parse_args())
        kwargs.pop("config", None)

        # Populate section= fields from the raw TOML (not from parsed args).
        section_fields = [f for f in dataclasses.fields(cls) if "section" in f.metadata]  # type: ignore[arg-type]
        full_toml = toml_data if section_fields else None

        return _reconstruct_config(cls, kwargs, full_toml)


# ---------------------------------------------------------------------------
# Module-level helpers: TOML loading and default injection
# ---------------------------------------------------------------------------


def _find_config_arg(argv: List[str]) -> Optional[str]:
    """Pre-scan argv for --config/-c without invoking the full parser."""
    for i, arg in enumerate(argv):
        if arg in ("--config", "-c") and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--config="):
            return arg.split("=", 1)[1]
    return None


def _load_toml(config_path: str) -> Dict[str, Any]:
    """Parse a TOML file and return its full contents as a dict."""
    try:
        import tomllib  # type: ignore[import]  # Python 3.11+
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(config_path) as f:
        return tomllib.loads(f.read())


def _toml_section_defaults(section_data: Dict[str, Any], cls: type) -> Dict[str, Any]:
    """Flatten a raw TOML section dict into argparse-compatible defaults.

    Normalises keys so that both 'my-field' and 'my_field' map to 'my_field'.
    Only returns keys that correspond to actual fields on cls (and its nested
    ConfigClass fields), so unrelated TOML keys are silently ignored.
    """
    field_names: set = set()
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        if is_config_class(f.type):
            for ff in dataclasses.fields(f.type):  # type: ignore[arg-type]
                field_names.add(ff.name)
        elif "subcommand" not in f.metadata and "section" not in f.metadata:
            field_names.add(f.name)

    return {key.replace("-", "_"): value for key, value in section_data.items() if key.replace("-", "_") in field_names}


def _env_defaults(cls: type) -> Dict[str, Any]:
    """Collect env-var values for fields that declare env_var= metadata.

    Applies the same type coercion that argparse would use for CLI values,
    so the value stored as a default is already the correct Python type.
    """
    result: Dict[str, Any] = {}
    for field in dataclasses.fields(cls):  # type: ignore[arg-type]
        if is_config_class(field.type):
            result.update(_env_defaults(field.type))  # type: ignore[arg-type]
            continue
        env_name = field.metadata.get("env_var")
        if env_name and env_name in os.environ:
            raw = os.environ[env_name]
            type_func = field.metadata.get("type") or get_type_args(field.type).get("type")
            result[field.name] = type_func(raw) if type_func else raw
    return result


# ---------------------------------------------------------------------------
# Module-level helpers: reconstruction from TOML / parsed-args dicts
# ---------------------------------------------------------------------------


def _reconstruct_from_toml(config_cls: Type[T], data: Dict[str, Any]) -> T:
    """Build a ConfigClass instance from a raw TOML section dict."""
    result_kwargs: Dict[str, Any] = {}
    for field in dataclasses.fields(config_cls):  # type: ignore[arg-type]
        if field.name not in data:
            continue
        if is_config_class(field.type):
            result_kwargs[field.name] = _reconstruct_from_toml(field.type, data[field.name])  # type: ignore[arg-type]
        else:
            result_kwargs[field.name] = data[field.name]
    return config_cls(**result_kwargs)


def _reconstruct_config(config_cls: Type[T], kwargs: Dict[str, Any], toml_data: Optional[Dict[str, Any]] = None) -> T:
    """Build a ConfigClass instance from a flat parsed-args dict.

    Pops only the fields belonging to config_cls from kwargs.
    Any remaining entries in kwargs are left for the caller.

    toml_data is the full parsed TOML dict; required when config_cls has
    fields with section= metadata.
    """
    result_kwargs: Dict[str, Any] = {}
    for field in dataclasses.fields(config_cls):  # type: ignore[arg-type]
        if "section" in field.metadata:
            section_name = field.metadata["section"]
            raw = (toml_data or {}).get(section_name)
            inner_cls = (
                get_list_type(field.type)
                if is_list(field.type)
                else get_optional_type(field.type) if is_optional(field.type) else field.type
            )
            if raw is None:
                result_kwargs[field.name] = [] if is_list(field.type) else None
            elif isinstance(raw, dict):
                instance = _reconstruct_from_toml(inner_cls, raw)  # type: ignore[arg-type]
                result_kwargs[field.name] = [instance] if is_list(field.type) else instance
            else:  # list of dicts — TOML [[array of tables]]
                result_kwargs[field.name] = [
                    _reconstruct_from_toml(inner_cls, item)  # type: ignore[arg-type]
                    for item in raw
                ]
        elif is_config_class(field.type):
            inner_kwargs: Dict[str, Any] = {}
            for f in dataclasses.fields(field.type):  # type: ignore[arg-type]
                if f.name in kwargs:
                    inner_kwargs[f.name] = kwargs.pop(f.name)
            result_kwargs[field.name] = field.type(**inner_kwargs)  # type: ignore[operator]
        elif field.name in kwargs:
            result_kwargs[field.name] = kwargs.pop(field.name)
    return config_cls(**result_kwargs)


# ---------------------------------------------------------------------------
# Module-level helpers: subparser tree construction and recursive reconstruction
# ---------------------------------------------------------------------------


def _build_subparser_tree(
    cls: type,
    parser: argparse.ArgumentParser,
    parent_cls: type,
    sections: List[str],
    dest: str,
    toml_data: Dict[str, Any],
) -> None:
    """Recursively add subparsers to *parser* for every subcommand field in *cls*.

    Args:
        cls:        The config class whose subcommand fields are being registered.
        parser:     The (sub)parser to attach the new subparsers to.
        parent_cls: The config class that owns *parser*; its non-subcommand fields
                    are registered on each subparser so they are available at every level.
        sections:   Accumulated TOML section names from all ancestor levels.
        dest:       Unique argparse dest name for this level's chosen subcommand.
        toml_data:  Full parsed TOML dict loaded from --config (may be empty).
    """
    subcommand_fields = [f for f in dataclasses.fields(cls) if "subcommand" in f.metadata]  # type: ignore[arg-type]
    if not subcommand_fields:
        return

    subparsers = parser.add_subparsers(dest=dest, required=True)

    for field in subcommand_fields:
        sub_section = field.metadata["subcommand"]
        config_cls = get_optional_type(field.type) if is_optional(field.type) else field.type
        level_sections = [s for s in sections + [sub_section] if s]

        subparser = subparsers.add_parser(field.name, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        subparser.add_argument("--config", "-c", metavar="FILE", help="Path to the TOML configuration file.")
        parent_cls.configure_parser(subparser)  # type: ignore[attr-defined]  # parent-level fields
        config_cls.configure_parser(subparser)  # type: ignore[union-attr]  # this sub-command's own fields

        # Inject TOML defaults: merge all ancestor sections + this sub-command's section.
        combined: Dict[str, Any] = {}
        for s in level_sections:
            combined.update(toml_data.get(s, {}))
        toml_defs = _toml_section_defaults(combined, config_cls)  # type: ignore[arg-type]
        if toml_defs:
            subparser.set_defaults(**toml_defs)

        # Env-var defaults override TOML.
        env_defs = _env_defaults(config_cls)  # type: ignore[arg-type]
        if env_defs:
            subparser.set_defaults(**env_defs)

        _build_subparser_tree(
            config_cls,  # type: ignore[arg-type]
            subparser,
            config_cls,  # type: ignore[arg-type]
            sections=level_sections,
            dest=f"{dest}_{field.name}",
            toml_data=toml_data,
        )


def _reconstruct_recursive(cls: Type[T], kwargs: Dict[str, Any], dest: str) -> T:
    """Recursively reconstruct a ConfigClass from a flat parsed-args dict."""
    subcommand_fields = [f for f in dataclasses.fields(cls) if "subcommand" in f.metadata]  # type: ignore[arg-type]

    if not subcommand_fields:
        return _reconstruct_config(cls, kwargs)

    subcommand = kwargs.pop(dest)
    sub_field = next(f for f in subcommand_fields if f.name == subcommand)
    config_cls = get_optional_type(sub_field.type) if is_optional(sub_field.type) else sub_field.type

    selected_config = _reconstruct_recursive(config_cls, kwargs, f"{dest}_{subcommand}")  # type: ignore[arg-type]

    wrapper_kwargs: Dict[str, Any] = {f.name: None for f in subcommand_fields}
    wrapper_kwargs[subcommand] = selected_config

    for field in dataclasses.fields(cls):  # type: ignore[arg-type]
        if "subcommand" in field.metadata:
            continue
        if is_config_class(field.type):
            inner_kwargs: Dict[str, Any] = {}
            for f in dataclasses.fields(field.type):  # type: ignore[arg-type]
                if f.name in kwargs:
                    inner_kwargs[f.name] = kwargs.pop(f.name)
            wrapper_kwargs[field.name] = field.type(**inner_kwargs)  # type: ignore[operator]
        elif field.name in kwargs:
            wrapper_kwargs[field.name] = kwargs.pop(field.name)

    return cls(**wrapper_kwargs)


# ---------------------------------------------------------------------------
# Type-parsing helpers
# ---------------------------------------------------------------------------


def parse_bool(s: str) -> bool:
    """parse a bool from a conventional string representation"""
    lower = s.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    raise argparse.ArgumentTypeError(f"'{s}' is not a valid bool")


def parse_enum(s: str, enumm: Type[enum.Enum]) -> Any:
    try:
        return enumm[s]
    except KeyError as e:
        raise argparse.ArgumentTypeError(f"'{s}' is not a valid {enumm.__name__}") from e


def is_optional(ty: Any) -> bool:
    """determines if `ty` is typing.Optional"""
    return typing.get_origin(ty) is typing.Union and typing.get_args(ty)[1] is type(None)


def get_optional_type(ty: Any) -> type:
    """get the `T` from a typing.Optional[T]"""
    return typing.get_args(ty)[0]


def is_list(ty: Any) -> bool:
    """determines if `ty` is typing.List or list"""
    return typing.get_origin(ty) is list or ty is list


def get_list_type(ty: Any) -> type:
    """get the generic type of a typing.List[T] or list[T]"""
    return typing.get_args(ty)[0]


def is_config_type(ty: Any) -> bool:
    """determines if ty is a subclass of ConfigType"""
    try:
        return issubclass(ty, ConfigType)
    except TypeError:
        return False


def is_config_class(ty: Any) -> bool:
    """determines if ty is a subclass of ConfigClass"""
    try:
        return issubclass(ty, ConfigClass)
    except TypeError:
        return False


def is_enum(ty: Any):
    """determines if ty is a subclass of Enum"""
    try:
        return issubclass(ty, enum.Enum)
    except TypeError:
        return False


def get_type_args(ty: Any) -> Dict[str, Any]:
    """
    The type of a field implies several options for its argument parsing,
    such as `type`, `nargs`, and `required`

    For example a parameter of type Option[T] is parsed as `T`,
    has no implication on `nargs`, and is not required

    Similarly a parameter of List[T] is also parsed as `T`,
    might have `nargs="*"`, and has no implication on `required`

    This function determines these settings based upon a given type.
    """

    # bools have special parsing so that they behave as users expect
    if ty is bool:
        return {"type": parse_bool}

    # for subclasses of ConfigType, we use the .from_string() method
    if is_config_type(ty):
        return {"type": ty.from_string}

    # recursing handles the case where e.g. the inner type is a bool
    # or a subclass of ConfigType, both of which need special handling
    #
    # parameters with this type are optional so we set `required=False`
    if is_optional(ty):
        opts = get_type_args(get_optional_type(ty))
        return {"type": opts["type"], "required": False}

    # `nargs="*"` is a reasonable default for lists that be overriden by the user
    # if other behaviour is desired
    if is_list(ty):
        opts = get_type_args(get_list_type(ty))
        return {"type": opts["type"], "nargs": "*"}

    # for enums we get their value by name
    if is_enum(ty):
        return {"type": lambda name: parse_enum(name, ty)}

    # the default, just use the type as-is
    return {"type": ty}
