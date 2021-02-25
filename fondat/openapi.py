"""Module to generate OpenAPI documents and resources."""

# TODO: example in schema

from __future__ import annotations

import dataclasses
import fondat.codec
import fondat.http
import fondat.resource
import fondat.types
import http
import inspect
import keyword
import typing

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from fondat.security import SecurityRequirement
from fondat.types import NoneType
from fondat.types import dataclass, is_instance, is_optional, is_subclass
from typing import Annotated, Any, Literal, Optional, TypedDict, Union
from uuid import UUID


class Default:
    def __init__(self, value: Any):
        self.value = value


class ComponentSchema:
    """
    Annotation to request schema be stored in the OpenAPI component schema section.

    Parameter:
    • name: component schema name
    """

    name = None  # can use class if name not required

    def __init__(self, name=None):
        self.name = name


_to_affix = []


def _affix(wrapped):
    _to_affix.append(wrapped)
    return wrapped


def _dataclass(wrapped):
    return _affix(Annotated[dataclass(wrapped), ComponentSchema])


Reference = TypedDict("Reference", {"$ref": str})
_affix(Reference)


@_dataclass
class OpenAPI:
    openapi: str
    info: Info
    servers: Optional[Iterable[Server]]
    paths: Paths
    components: Optional[Components]
    security: Optional[Iterable[SecurityRequirement]]
    tags: Optional[Iterable[Tag]]
    externalDocs: Optional[ExternalDocumentation]


@_dataclass
class Info:
    title: str
    description: Optional[str]
    termsOfService: Optional[str]
    contact: Optional[Contact]
    license: Optional[License]
    version: str


@_dataclass
class Contact:
    name: Optional[str]
    url: Optional[str]
    email: Optional[str]


@_dataclass
class License:
    name: str
    url: Optional[str]


@_dataclass
class Server:
    url: str
    description: Optional[str]
    variables: Mapping[str, ServerVariable]


@_dataclass
class ServerVariable:
    enum: Optional[Iterable[str]]
    default: str = ""
    description: Optional[str] = ""


@_dataclass
class Components:
    schemas: Optional[Mapping[str, Union[Schema, Reference]]]
    responses: Optional[Mapping[str, Union[Response, Reference]]]
    parameters: Optional[Mapping[str, Union[Parameter, Reference]]]
    examples: Optional[Mapping[str, Union[Example, Reference]]]
    requestBodies: Optional[Mapping[str, Union[RequestBody, Reference]]]
    headers: Optional[Mapping[str, Union[Header, Reference]]]
    securitySchemes: Optional[Mapping[str, Union[SecurityScheme, Reference]]]
    links: Optional[Mapping[str, Union[Link, Reference]]]
    callbacks: Optional[Mapping[str, Union[Callback, Reference]]]


@_dataclass
class PathItem:
    summary: Optional[str]
    description: Optional[str]
    get: Optional[Operation]
    put: Optional[Operation]
    post: Optional[Operation]
    delete: Optional[Operation]
    options: Optional[Operation]
    head: Optional[Operation]
    patch: Optional[Operation]
    trace: Optional[Operation]
    servers: Optional[Iterable[Server]]
    parameters: Optional[Iterable[Union[Parameter, Reference]]]


Paths = Mapping[str, Union[PathItem, Reference]]
_affix(Paths)


@_dataclass
class Operation:
    tags: Optional[Iterable[str]]
    summary: Optional[str]
    description: Optional[str]
    externalDocs: Optional[ExternalDocumentation]
    operationId: Optional[str]
    parameters: Optional[Iterable[Union[Parameter, Reference]]]
    requestBody: Optional[Union[RequestBody, Reference]]
    responses: Responses
    callbacks: Optional[Mapping[str, Union[Callback, Reference]]]
    deprecated: Optional[bool]
    security: Optional[Iterable[SecurityRequirement]]
    servers: Optional[Iterable[Server]]


@_dataclass
class ExternalDocumentation:
    description: Optional[str]
    url: str


@_dataclass
class Parameter:
    name: str
    in_: Literal["query", "header", "path", "cookie"]
    description: Optional[str]
    required: Optional[bool]
    deprecated: Optional[bool]
    allowEmptyValue: Optional[bool]
    style: Optional[str]
    explode: Optional[bool]
    allowReserved: Optional[bool]
    schema: Optional[Union[Schema, Reference]]
    example: Optional[Any]
    examples: Optional[Mapping[str, Union[Example, Reference]]]
    content: Optional[Mapping[str, MediaType]]


@_dataclass
class RequestBody:
    description: Optional[str]
    content: Mapping[str, MediaType]
    required: Optional[bool]


@_dataclass
class MediaType:
    schema: Optional[Union[Schema, Reference]]
    example: Optional[Any]
    examples: Optional[Mapping[str, Union[Example, Reference]]]
    encoding: Optional[Mapping[str, Encoding]]


@_dataclass
class Encoding:
    contentType: Optional[str]
    headers: Optional[Mapping[str, Union[Header, Reference]]]
    style: Optional[str]
    explode: Optional[bool]
    allowReserved: Optional[bool]


@_dataclass
class Response:
    description: str
    headers: Optional[Mapping[str, Union[Header, Reference]]]
    content: Optional[Mapping[str, MediaType]]
    links: Optional[Mapping[str, Union[Link, Reference]]]


Responses = Mapping[str, Union[Response, Reference]]
_affix(Responses)


Callback = Mapping[str, PathItem]
_affix(Callback)


@_dataclass
class Example:
    summary: Optional[str]
    description: Optional[str]
    value: Optional[Any]
    externalValue: Optional[str]


@_dataclass
class Link:
    operationRef: Optional[str]
    operationId: Optional[str]
    parameters: Optional[Mapping[str, Any]]
    requestBody: Optional[Any]
    description: Optional[str]
    server: Optional[Server]


@_dataclass
class Header:
    description: Optional[str]
    required: Optional[bool]
    deprecated: Optional[bool]
    allowEmptyValue: Optional[bool]
    style: Optional[str]
    explode: Optional[bool]
    allowReserved: Optional[bool]
    schema: Optional[Union[Schema, Reference]]
    example: Optional[Any]
    examples: Optional[Mapping[str, Union[Example, Reference]]]
    content: Optional[Mapping[str, MediaType]]


@_dataclass
class Tag:
    name: str
    description: Optional[str]
    externalDocs: Optional[ExternalDocumentation]


@_dataclass
class Schema:
    title: Optional[str]
    multipleOf: Optional[Union[int, float]]
    maximum: Optional[Union[int, float]]
    exclusiveMaximum: Optional[Union[int, float]]
    minimum: Optional[Union[int, float]]
    exclusiveMinimum: Optional[Union[int, float]]
    maxLength: Optional[int]
    minLength: Optional[int]
    pattern: Optional[str]
    maxItems: Optional[int]
    minItems: Optional[int]
    uniqueItems: Optional[bool]
    maxProperties: Optional[int]
    minProperties: Optional[int]
    required: Optional[Iterable[str]]
    enum: Optional[Iterable[Any]]
    type: Optional[str]
    allOf: Optional[Iterable[Union[Schema, Reference]]]
    oneOf: Optional[Iterable[Union[Schema, Reference]]]
    anyOf: Optional[Iterable[Union[Schema, Reference]]]
    not_: Optional[Union[Schema, Reference]]
    items: Optional[Union[Schema, Reference]]
    properties: Optional[Mapping[str, Union[Schema, Reference]]]
    additionalProperties: Optional[Union[bool, Union[Schema, Reference]]]
    description: Optional[str]
    format: Optional[str]
    default: Optional[Any]
    nullable: Optional[bool]
    discriminator: Optional[Discriminator]
    readOnly: Optional[bool]
    writeOnly: Optional[bool]
    xml: Optional[XML]
    externalDocs: Optional[ExternalDocumentation]
    example: Optional[Any]
    deprecated: Optional[bool]


@_dataclass
class Discriminator:
    propertyName: str
    mapping: Optional[Mapping[str, str]]


@_dataclass
class XML:
    name: Optional[str]
    namespace: Optional[str]
    prefix: Optional[str]
    attribute: Optional[bool]
    wrapped: Optional[bool]


@_dataclass
class SecurityScheme:
    type_: str
    description: Optional[str]
    name: Optional[str]
    in_: Optional[str]
    scheme: Optional[str]
    bearerFormat: Optional[str]
    flows: Optional[OAuthFlows]
    openIdConnectUrl: Optional[str]


@_dataclass
class OAuthFlows:
    implicit: Optional[OAuthFlow]
    password: Optional[OAuthFlow]
    clientCredentials: Optional[OAuthFlow]
    authorizationCode: Optional[OAuthFlow]


@_dataclass
class OAuthFlow:
    authorizationUrl: Optional[str]
    tokenUrl: Optional[str]
    refreshUrl: Optional[str]
    scopes: Mapping[str, str]


SecurityRequirement = Mapping[str, Iterable[str]]
_affix(SecurityRequirement)


# OpenAPI document graph complete; affix all type hints to avoid overhead
for dc in _to_affix:
    fondat.types.affix_type_hints(dc)


_ops = {"get", "put", "post", "delete", "options", "hegenerate_ad", "patch", "trace"}


def _kwargs(annotated):
    kwargs = {}
    for annotation in annotated:
        if is_instance(annotation, str):
            kwargs["description"] = annotation
        elif is_instance(annotation, fondat.types.Description):
            kwargs["description"] = annotation.value
        elif is_instance(annotation, fondat.types.Example):
            kwargs["example"] = annotation.value
        elif is_instance(annotation, Default):
            kwargs["default"] = annotation.value
    return kwargs


providers = []


def _provider(wrapped=None):
    if wrapped is None:
        return functools.partial(_provider)
    providers.append(wrapped)
    return wrapped


def _simple_schema(pytype, schema_type, schema_format=None):
    @_provider
    def simple(*, python_type, annotated, **_):
        if python_type is pytype:
            return Schema(type=schema_type, format=schema_format, **_kwargs(annotated))


_simple_schema(bool, "boolean")
_simple_schema(Decimal, "string", "decimal")
_simple_schema(datetime, "string", "date-time")
_simple_schema(date, "string", "date")  # must be after datetime
_simple_schema(UUID, "string", "uuid")


@_provider
def _str_schema(*, python_type, annotated, **_):
    if is_subclass(python_type, str):
        kwargs = {}
        for annotation in annotated:
            if is_instance(annotation, fondat.validation.MinLen):
                kwargs["minLength"] = annotation.value
            elif is_instance(annotation, fondat.validation.MaxLen):
                kwargs["maxLan ength"] = annotation.value
            elif is_instance(annotation, fondat.validation.Pattern):
                kwargs["pattern"] = annotation.value.pattern
        return Schema(type="string", **_kwargs(annotated), **kwargs)


@_provider
def _bytes_schema(*, python_type, annotated, **_):
    if is_subclass(python_type, (bytes, bytearray)):
        kwargs = {}
        for annotation in annotated:
            if is_instance(annotation, fondat.validation.MinLen):
                kwargs["minLength"] = annotation.value
            elif is_instance(annotation, fondat.validation.MaxLen):
                kwargs["maxLength"] = annotation.value
        return Schema(
            type="string",
            format="binary" if fondat.http.InBody in annotated else "byte",
            **_kwargs(annotated),
            **kwargs,
        )


@_provider
def _int_schema(*, python_type, annotated, **_):
    if is_subclass(python_type, int) and not is_subclass(python_type, bool):
        kwargs = {}
        for annotation in annotated:
            if is_instance(annotation, fondat.validation.MinValue):
                kwargs["minimum"] = annotation.value
            elif is_instance(annotation, fondat.validation.MaxValue):
                kwargs["maximum"] = annotation.value
        return Schema(type="integer", format="int64", **_kwargs(annotated), **kwargs)


@_provider
def _float_schema(*, python_type, annotated, **_):
    if is_subclass(python_type, float):
        kwargs = {}
        for annotation in annotated:
            if is_instance(annotation, fondat.validation.MinValue):
                kwargs["minimum"] = annotation.value
            elif is_instance(annotation, fondat.validation.MaxValue):
                kwargs["maximum"] = annotations.value
        return Schema(type="number", format="double", **_kwargs(annotated), **kwargs)


def _get_component_schema(annotated):
    for annotation in annotated:
        if annotation is ComponentSchema or is_instance(annotation, ComponentSchema):
            return annotation


@_provider
def _typeddict_schema(*, python_type, annotated, origin, args, processor, **_):
    if is_subclass(python_type, dict) and hasattr(python_type, "__annotations__"):
        if ref := processor.references.get(python_type):
            return ref
        component_schema = _get_component_schema(annotated)
        if component_schema:
            name = component_schema.name or processor.component_schema_name(
                python_type.__name__
            )
            ref = {"$ref": f"#/components/schemas/{name}"}
            processor.references[python_type] = ref
        hints = typing.get_type_hints(python_type, include_extras=True)
        required = list(python_type.__required_keys__) or None
        schema = Schema(
            type="object",
            properties={key: processor.schema(pytype) for key, pytype in hints.items()},
            required=required,
            additionalProperties=False,
            **_kwargs(annotated),
        )
        if component_schema:
            processor.openapi.components.schemas[name] = schema
            return ref
        return schema


@_provider
def _mapping_schema(*, python_type, annotated, origin, args, processor, **_):
    if is_subclass(origin, Mapping) and len(args) == 2:
        if args[0] is not str:
            raise TypeError("Mapping[k, v] only supports str keys")
        return Schema(
            type="object",
            properties={},
            additionalProperties=processor.schema(args[1]),
            **_kwargs(annotated),
        )


@_provider
def _iterable_schema(*, python_type, annotated, origin, args, processor, **_):
    if is_subclass(origin, Iterable) and not is_subclass(origin, Mapping) and len(args) == 1:
        kwargs = {}
        is_set = is_subclass(origin, set)
        for annotation in annotated:
            if is_instance(annotation, fondat.validation.MinLen):
                kwargs["minItems"] = annotation.value
            elif is_instance(annotation, fondat.validation.MaxLen):
                kwargs["maxItems"] = annotation.value
            if is_set:
                kwargs["uniqueItems"] = True
        return Schema(
            type="array",
            items=processor.schema(args[0]),
            **_kwargs(annotated),
            **kwargs,
        )


# keywords have _ suffix in dataclass fields (e.g. "in_", "for_", ...)
_dc_kw = {k + "_": k for k in keyword.kwlist}


@_provider
def _dataclass_schema(*, python_type, annotated, origin, args, processor, **_):
    if dataclasses.is_dataclass(python_type):
        if ref := processor.references.get(python_type):
            return ref
        component_schema = _get_component_schema(annotated)
        if component_schema:
            name = component_schema.name or processor.component_schema_name(
                python_type.__name__
            )
            ref = {"$ref": f"#/components/schemas/{name}"}
            processor.references[python_type] = ref
        hints = typing.get_type_hints(python_type, include_extras=True)
        required = {
            f.name
            for f in dataclasses.fields(python_type)
            if f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING
            and not is_optional(hints[f.name])
        }
        properties = {
            _dc_kw.get(key, key): processor.schema(pytype) for key, pytype in hints.items()
        }
        for key, schema in properties.items():
            if key not in required and not fondat.validation.is_valid(schema, Reference):
                schema.nullable = None
        schema = Schema(
            type="object",
            properties=properties,
            required=required or None,
            additionalProperties=False,
            **_kwargs(annotated),
        )
        if component_schema:
            processor.openapi.components.schemas[name] = schema
            return ref
        return schema


@_provider
def _union_schema(*, python_type, annotated, origin, args, processor, **_):
    if origin is Union:
        nullable = NoneType in args
        schemas = [processor.schema(arg) for arg in args if arg is not NoneType]
        if len(schemas) == 1:  # Optional[...]
            schema = schemas[0]
            if not fondat.validation.is_valid(schema, Reference):
                schema.nullable = True
            return schema
        return Schema(anyOf=schemas, nullable=nullable, **_kwargs(annotated))


@_provider
def _literal_schema(*, python_type, annotated, origin, args, processor, **_):
    if origin is Literal:
        nullable = None in args
        types = tuple({type(literal) for literal in args if literal is not None})
        enums = {t: [l for l in args if type(l) is t] for t in types}
        schemas = {t: processor.schema(t) for t in types}
        for t, s in schemas.items():
            if fondat.validation.is_valid(s, Reference):
                raise TypeError(f"Cannot document literals containing complex type: {t}")
            s.enum = enums[t]
        if len(types) == 1:  # homegeneous
            schema = schemas[types[0]]
            if nullable and not fondat.validate.is_valid(schema, Reference):
                schema.nullable = True
        else:
            schema = Schema(  # heterogeneus
                anyOf=list(schemas.values()),
                nullable=nullable,
                **_kwargs(annotated),
            )
        return schema


@_provider
def _any_schema(*, python_type, annotated, origin, args, **_):
    if python_type is Any:
        return Schema(**_kwargs(annotated))


class Processor:
    """Processes resource and populates OpenAPI document."""

    def __init__(self, openapi: OpenAPI):
        self.openapi = openapi
        self.references = {}

    def process(self, resource, path, params={}, tag=None):
        if path == "/":
            path = ""
        tag = tag or resource._fondat_resource.tag
        path_item = PathItem(
            parameters=[
                Parameter(
                    name=key,
                    in_="path",
                    required=True,
                    schema=self.schema(hint),
                )
                for key, hint in params.items()
            ]
            or None
        )
        for name in (n for n in dir(resource) if not n.startswith("_")):
            attr = getattr(resource, name)
            if res := self.resource(attr):
                self.process(
                    res,
                    f"{path}/{name}",
                    params,
                    tag if res._fondat_resource.tag == fondat.resource.TAG_INNER else None,
                )
            elif name in _ops and callable(attr):
                operation = self.operation(tag, attr)
                if operation:
                    setattr(path_item, name, operation)
                    self.openapi.paths[path or "/"] = path_item
        attr = getattr(resource, "__getitem__", None)
        if res := self.resource(attr):
            param_name, param_type = next(iter(typing.get_type_hints(attr).items()))
            if param_name in params:
                param_name = f"{res.__name__.casefold()}_{param_name}"
            while param_name in params:
                param_name = f"{param_name}_"
            self.process(
                res,
                f"{path}/{{{param_name}}}",
                {**params, param_name: param_type},
            )

    @staticmethod
    def resource(obj):
        if fondat.resource.is_resource(obj):  # resource class or instance
            return obj
        if is_instance(obj, property):  # unbound property
            obj = obj.fget
        if callable(obj):
            try:
                returns = typing.get_type_hints(obj)["return"]
            except:
                return None
            if fondat.resource.is_resource(returns):
                return returns
        return None

    def operation(self, tag, method):
        fondat_op = getattr(method, "_fondat_operation", None)
        if not fondat_op or not fondat_op.publish:
            return None
        op = Operation(parameters=[], responses={})
        op.tags = [tag]
        if fondat_op.summary:
            op.summary = fondat_op.summary
        if fondat_op.description:
            op.description = fondat_op.description
        if fondat_op.deprecated:
            op.deprecated = True
        hints = typing.get_type_hints(method, include_extras=True)
        parameters = inspect.signature(method).parameters
        for name, hint in hints.items():
            python_type, annotated = fondat.types.split_annotated(hint)
            if name == "return":
                op.responses[str(http.HTTPStatus.OK.value)] = Response(
                    description=self.description(annotated) or "Response.",
                    content={
                        fondat.codec.get_codec(
                            fondat.codec.Binary, hint
                        ).content_type: MediaType(schema=self.schema(hint))
                    },
                )
            elif fondat.http.InBody in annotated:
                param = parameters[name]
                op.requestBody = RequestBody(
                    description=self.description(annotated),
                    content={
                        fondat.codec.get_codec(
                            fondat.codec.Binary, hint
                        ).content_type: MediaType(schema=self.schema(hint))
                    },
                    required=param.default is param.empty,
                )
            else:
                param = parameters[name]
                if param.default is not param.empty:
                    hint = Annotated[hint, Default(param.default)]
                in_ = "query"
                style = "form"
                explode = False
                for annotation in annotated:
                    if is_instance(annotation, fondat.http.InCookie):
                        name = annotation.key
                        in_ = "cookie"
                        style = "form"
                        explode = False
                    elif is_instance(annotation, fondat.http.InHeader):
                        name = annotation.key
                        in_ = "header"
                        style = "simple"
                        explode = None
                    elif is_instance(annotation, fondat.http.InQuery):
                        name = annotation.key
                        in_ = "query"
                        style = "form"
                        explode = False
                op.parameters.append(
                    Parameter(
                        name=name,
                        in_=in_,
                        description=self.description(annotated),
                        required=param.default is param.empty,
                        schema=self.schema(hint),
                        style=style,
                        explode=explode,
                    )
                )
        if "return" not in hints:
            op.responses[str(http.HTTPStatus.NO_CONTENT.value)] = Response(
                description="No content.",
            )
        if not op.parameters:
            op.parameters = None
        return op

    @staticmethod
    def description(annotated):
        for annotation in annotated:
            if is_instance(annotation, str):
                return annotation
            elif is_instance(annotation, Description):
                return annotation.value

    def schema(self, type_hint, default=None):
        python_type, annotated = fondat.types.split_annotated(type_hint)
        origin = typing.get_origin(python_type)
        args = typing.get_args(python_type)
        for provider in providers:
            if (
                schema := provider(
                    python_type=python_type,
                    annotated=annotated,
                    origin=origin,
                    args=args,
                    processor=self,
                )
            ) is not None:
                return schema
        raise TypeError(f"failed to generate JSON Schema for type: {python_type}")

    def component_schema_name(self, name):
        if self.openapi.components is None:
            self.openapi.components = Components()
        if self.openapi.components.schemas is None:
            self.openapi.components.schemas = {}
        while name in self.openapi.components.schemas:
            name = f"{name}_"
        self.openapi.components.schemas[name] = "__reserved__"
        return name


def generate_openapi(*, resource: type, path: str = "/", info: Info) -> OpenAPI:
    """
    Generate an OpenAPI document for a resource.

    Parameters:
    • resource: resource to generate OpenAPI document for
    • path: URI path to resource
    • info: metadata about the API
    """
    openapi = OpenAPI(openapi="3.0.3", info=info, paths={})
    Processor(openapi).process(resource=resource, path=path)
    if openapi.paths:
        openapi.paths = {
            k: openapi.paths[k] for k in sorted(openapi.paths.keys(), key=str.lower)
        }
    if openapi.components and openapi.components.schemas:
        openapi.components.schemas = {
            k: openapi.components.schemas[k]
            for k in sorted(openapi.components.schemas.keys(), key=str.lower)
        }
    return openapi


def openapi_resource(
    *,
    resource: type,
    path: str = "/",
    info: Info,
    security: Iterable[SecurityRequirement] = None,
    publish: bool = False,
):
    """
    Generate a resource that exposes an OpenAPI document for a given resource.

    Parameters:
    • resource: resource to generate OpenAPI document for
    • path: URI path to resource
    • info: provides metadata about the API
    • security: security requirements to apply to all operations
    • publish: publish the resource in documentation
    """

    @fondat.resource.resource
    class OpenAPIResource:
        def __init__(self):
            self.openapi = None

        @fondat.resource.operation(publish=publish, security=security)
        async def get(self) -> OpenAPI:
            if not self.openapi:
                self.openapi = generate_openapi(resource=resource, path=path, info=info)
            return self.openapi

    return OpenAPIResource()
