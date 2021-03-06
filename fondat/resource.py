"""
Module to implement resources composed of operations.

A resource is an addressible object that exposes operations through a uniform set of methods.

A resource class contains operation methods, each decorated with the @operation decorator.

A resource can expose inner (subordinate) resources through an attribute, method or property
that is decorated as a resource.
"""

import asyncio
import functools
import inspect
import fondat.context as context
import fondat.lazy
import fondat.monitoring as monitoring
import fondat.validation
import logging
import threading
import types
import wrapt

from collections.abc import Iterable, Mapping
from fondat.error import ForbiddenError, UnauthorizedError
from fondat.security import SecurityRequirement
from typing import Any, Literal


_logger = logging.getLogger(__name__)


def _summary(function):
    """
    Derive summary information from a function's docstring or name. The summary is the first
    sentence of the docstring, ending in a period, or if no dostring is present, the
    function's name capitalized.
    """
    if not function.__doc__:
        return f"{function.__name__.capitalize()}."
    result = []
    for word in function.__doc__.split():
        result.append(word)
        if word.endswith("."):
            break
    return " ".join(result)


async def authorize(security):
    """
    Peform authorization of an operation.

    Parameters:
    • security: iterable of security requirements

    Security exceptions are: UnauthorizedError and ForbiddenError.

    This coroutine function executes the security requirements in the order specified. If any
    security requirement does not raise a security exception, then this coroutine passes and
    authorization is granted.

    If a security requirement raises a non-security exception, then that exception is
    immediately re-raised.  If security requrements raise a mixture of ForbiddenError and
    UnauthorizedError exceptions, then the first ForbiddenError is re-raised. If only
    UnautorizedError exceptions are raised, then the first UnauthorizedError is re-raised.
    """
    exception = None
    for requirement in security or ():
        try:
            await requirement.authorize()
            return  # security requirement authorized the operation
        except ForbiddenError as fe:
            if not isinstance(exception, ForbiddenException):
                exception = fe
        except UnauthorizedError as ue:
            if not exception:
                exception = ue
        except:
            raise
    if exception:
        raise exception


def resource(wrapped=None, *, tag=None):
    """
    Decorate a class to be a resource containing operations.

    Parameters:
    • tag: tag to group resources  [resource class name]
    """

    if wrapped is None:
        return functools.partial(resource, tag=tag)

    wrapped._fondat_resource = types.SimpleNamespace(tag=tag or wrapped.__name__)

    return wrapped


def is_resource(obj_or_type: Any) -> bool:
    """Return if object or type represents a resource."""
    return getattr(obj_or_type, "_fondat_resource", None) is not None


def is_operation(obj_or_type: Any) -> bool:
    """Return if object represents a resource operation."""
    return getattr(obj_or_type, "_fondat_operation", None) is not None


def operation(
    wrapped=None,
    *,
    op_type: Literal["query", "mutation"] = None,
    security: Iterable[SecurityRequirement] = None,
    publish: bool = True,
    deprecated: bool = False,
    validate: bool = True,
):
    """
    Decorate a resource coroutine that performs an operation.

    Parameters:
    • op_type: operation type
    • security: security requirements for the operation
    • publish: publish the operation in documentation
    • deprecated: declare the operation as deprecated
    • validate: validate method arguments

    Resource operations should correlate to HTTP method names, named in lower case. For
    example: get, put, post, delete, patch. Operation type is inferred from method name.
    """

    if wrapped is None:
        return functools.partial(
            operation,
            publish=publish,
            security=security,
            deprecated=deprecated,
            validate=validate,
        )

    if not asyncio.iscoroutinefunction(wrapped):
        raise TypeError("operation must be a coroutine")

    op_type = op_type or "query" if wrapped.__name__ == "get" else "mutation"
    name = wrapped.__name__
    description = wrapped.__doc__ or name
    summary = _summary(wrapped)

    for p in inspect.signature(wrapped).parameters.values():
        if p.kind is p.VAR_POSITIONAL:
            raise TypeError("operation with *args is not supported")
        elif p.kind is p.VAR_KEYWORD:
            raise TypeError("operation with **kwargs is not supported")

    @wrapt.decorator
    async def wrapper(wrapped, instance, args, kwargs):
        operation = getattr(wrapped, "_fondat_operation")
        res_name = f"{instance.__class__.__module__}.{instance.__class__.__qualname__}"
        op_name = wrapped.__name__
        tags = {"resource": res_name, "operation": op_name}
        _logger.debug("%s.%s(args=%s, kwargs=%s)", res_name, op_name, args, kwargs)
        with context.push({"context": "fondat.operation", **tags}):
            async with monitoring.timer({"name": "operation_duration_seconds", **tags}):
                async with monitoring.counter({"name": "operation_calls_total", **tags}):
                    await authorize(operation.security)
                    return await wrapped(*args, **kwargs)

    wrapped._fondat_operation = types.SimpleNamespace(
        op_type=op_type,
        summary=summary,
        description=description,
        publish=publish,
        security=security,
        deprecated=deprecated,
    )

    if validate:
        wrapped = fondat.validation.validate_arguments(wrapped)

    return wrapper(wrapped)


# A resource tagged with TAG_INNER shall inherit the tag from its outer (superior) resource.
TAG_INNER = "__inner__"


def inner(
    wrapped=None,
    *,
    method: str,
    op_type: str = None,
    publish: bool = True,
    security: Iterable[SecurityRequirement] = None,
    validate: bool = True,
):
    """
    Decorator to define an inner resource operation.

    Parameters:
    • method: name of method to implement (e.g "get")
    • publish: publish the operation in documentation
    • security: security requirements for the operation
    • validate: validate method arguments

    This decorator creates a new resource class, with a single operation that implements the
    decorated method. The decorated method is bound to the original outer resource instance
    where it was defined.
    """

    if wrapped is None:
        return functools.partial(
            inner,
            method=method,
            op_type=op_type,
            publish=publish,
            security=security,
            validate=validate,
        )

    if not asyncio.iscoroutinefunction(wrapped):
        raise TypeError("inner resource method must be a coroutine")

    if not method:
        raise TypeError("method name is required")

    _wrapped = wrapped

    if validate:
        _wrapped = fondat.validation.validate_arguments(_wrapped)

    @resource(tag=TAG_INNER)
    class Inner:
        def __init__(self, outer):
            self._outer = outer

    Inner.__doc__ = wrapped.__doc__
    Inner.__name__ = wrapped.__name__.title().replace("_", "")
    Inner.__qualname__ = Inner.__name__
    Inner.__module__ = wrapped.__module__

    async def proxy(self, *args, **kwargs):
        return await types.MethodType(_wrapped, self._outer)(*args, **kwargs)

    functools.update_wrapper(proxy, wrapped)
    proxy.__name__ = method
    proxy = operation(proxy, publish=publish, security=security, validate=False)
    setattr(Inner, method, proxy)
    setattr(Inner, "__call__", proxy)

    def res(self) -> Inner:
        return Inner(self)

    res.__doc__ = wrapped.__doc__
    res.__module__ = wrapped.__module__
    res.__name__ = wrapped.__name__
    res.__qualname__ = wrapped.__qualname__
    res.__annotations__ = {"return": Inner}

    return property(res)


def query(wrapped=None, *, method: str = "get", **kwargs):
    """Decorator to define an inner resource query operation."""

    if wrapped is None:
        return functools.partial(
            query,
            method=method,
            **kwargs,
        )

    return inner(wrapped, op_type="query", method=method, **kwargs)


def mutation(wrapped=None, *, method: str = "post", **kwargs):
    """Decorator to define an inner resource mutation operation."""

    if wrapped is None:
        return functools.partial(
            mutation,
            method=method,
            **kwargs,
        )

    return inner(wrapped, op_type="mutation", method=method, **kwargs)


def container_resource(resources: Mapping[str, type], tag: str = None):
    """
    Create a resource to contain subordinate resources.

    Parameters:
    • resources: mapping of resource names to resource objects
    • tag: tag to group the resource

    Suborindates are accessed as attributes by name.
    """

    @resource(tag=tag)
    class Container:
        def __getattr__(self, name):
            try:
                return resources[name]
            except KeyError:
                raise AttributeError(f"no such resource: {name}")

        def __dir__(self):
            return [*super().__dir__(), *resources.keys()]

    return Container()
