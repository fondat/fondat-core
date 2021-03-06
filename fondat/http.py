"""Module to expose resources through HTTP."""

import asyncio
import fondat.error
import fondat.resource
import fondat.security
import http
import http.cookies
import inspect
import json
import logging
import multidict
import typing

from collections.abc import Callable, Iterable, MutableSequence
from fondat.codec import Binary, String, get_codec
from fondat.types import Stream, BytesStream, is_optional, is_subclass
from fondat.validation import validate
from typing import Annotated, Any, Literal


_logger = logging.getLogger(__name__)


Headers = multidict.CIMultiDict
Cookies = http.cookies.SimpleCookie
Query = multidict.MultiDict


class Message:
    """
    Base class for HTTP request and response.

    Parameters and attributes:
    • headers: multi-value dictionary to store headers; excludes cookies
    • cookies: dictionary containing message cookies
    • body: stream message body, or None if no body
    """

    def __init__(
        self,
        *,
        headers: Headers = None,
        cookies: Cookies = None,
        body: Stream = None,
    ):
        super().__init__()
        self.headers = headers or Headers()
        self.cookies = cookies or Cookies()
        self.body = body


class Request(Message):
    """
    HTTP request.

    Parameters and attributes:
    • headers: multi-value dictionary to store headers; excludes cookies
    • cookies: simple cookie object to store request cookies
    • body: stream for request body, or None
    • method: the HTTP method name, in upper case
    • path: HTTP request target excluding query string
    • version: version of the incoming HTTP request
    • query: multi-value dictionary to store query string parameters
    """

    def __init__(
        self,
        *,
        headers: Headers = None,
        cookies: Cookies = None,
        body: Stream = None,
        method: str = "GET",
        path: str = "/",
        version: str = "1.1",
        query: Query = None,
    ):
        super().__init__(headers=headers, cookies=cookies, body=body)
        self.method = method
        self.path = path
        self.version = version
        self.query = query or Query()


class Response(Message):
    """
    HTTP response.

    Parameters and attributes:
    • headers: multi-value dictionary to store headers; excludes cookies
    • cookies: dictionary containing response cookies
    • body: stream for response body, or None
    • status: HTTP status code
    """

    def __init__(
        self,
        *,
        headers: Headers = None,
        cookies: Cookies = None,
        body: Stream = None,
        status: int = http.HTTPStatus.OK.value,
    ):
        super().__init__(headers=headers, cookies=cookies, body=body)
        self.status = status


class Chain:
    """
    A chain of zero or more filters, terminated by a single handler.

    A handler is a coroutine function that inspects a request and returns a response. A chain
    is itself a request handler.

    A filter is either a coroutine function or an asynchronous generator.

    A coroutine function filter can inspect and modify a request, and:
    • return no value to indicate that the filter passed; processing continues down the chain
    • return a response; the request is not processed by any subsequent filters or handler

    An asynchronous generator filter can inspect and modify a request, and:
    • yield no value; processing continues down the chain
    • yield a response; the request is not processed by any subsequent filters or handler

    The response from handler and downstream filters is sent to the asynchronous generator
    filter and becomes the result of the yield expression. The filter can then inspect and
    modify the response, and:
    • yield no value; the existing response is passed back up the chain
    • yield a new response; this response is passed back up the chain to the caller
    """

    def __init__(self, *, filters: MutableSequence[Callable] = None, handler: Callable):
        """Initialize a filter chain."""
        self.filters = filters  # concrete and mutable
        self.handler = handler

    async def handle(self, request):
        """Handle a request."""
        rewind = []
        response = None
        for filter in (f(request) for f in self.filters):
            if inspect.isasyncgen(filter):
                try:
                    response = await filter.__anext__()
                    if response:  # yielded a response
                        break
                    rewind.append(filter)
                except StopAsyncIteration:
                    pass
            elif asyncio.iscoroutine(filter):
                response = await filter
                if response:  # yielded a response
                    break
        if not response:
            response = await self.handler(request)
        for filter in reversed(rewind):
            try:
                _response = await filter.asend(response)
                if _response:  # yielded a new response
                    response = _response
            except StopAsyncIteration:
                pass
        return response


class HTTPSecurityScheme(fondat.security.SecurityScheme):
    """
    Base class for HTTP authentication security scheme.

    Parameters:
    • name: name of the security scheme
    • scheme: name of the HTTP authorization scheme
    • description: a short description for the security scheme
    """

    def __init__(self, name: str, scheme: str, **kwargs):
        super().__init__(name, "http", **kwargs)
        self.scheme = scheme

    # TODO: move to OpenAPI
    @property
    def json(self):
        """JSON representation of the security scheme."""
        result = super().json
        result["scheme"] = self.scheme
        return result


class HTTPBasicSecurityScheme(HTTPSecurityScheme):
    """
    Base class for HTTP basic authentication security scheme. Subclass must implement the
    authenticate method.

    Parameters:
    • name: name of the security scheme
    • realm: realm to include in the challenge  [name]
    • description: a short description for the security scheme
    """

    def __init__(self, name: str, realm: str = None, **kwargs):
        super().__init__(name, "basic", **kwargs)
        self.realm = realm or name

    async def filter(self, request):
        """
        Filters the incoming HTTP request. If the request contains credentials in the HTTP
        Basic authentication scheme, they are passed to the authenticate method. If
        authentication is successful, a context is added to the context stack.
        """
        auth = None
        header = request.headers.get("Authorization")
        if header and request.authorization[0].lower() == "basic":
            try:
                user_id, password = (
                    base64.b64decode(request.authorization[1]).decode().split(":", 1)
                )
            except (binascii.Error, UnicodeDecodeError):
                pass
            else:
                auth = await self.authenticate(user_id, password)
        with fondat.context.push(auth) if auth else contextlib.nullcontext():
            yield

    async def authenticate(user_id, password):
        """
        Perform authentication of credentials supplied in the HTTP request. If authentication
        is successful, a context is returned to be pushed on the context stack. If
        authentication fails, None is returned. This method should not raise an exception
        unless an unrecoverable error occurs.
        """
        raise NotImplementedError


class APIKeySecurityScheme(fondat.security.SecurityScheme):
    """
    Base class for API key authentication security scheme. Subclass must implement the
    authenticate method.

    Parameters:
    • name: name of the security scheme
    • key: name of API key to be used
    • location: location of API key
    • description: a short description for the security scheme
    """

    def __init__(self, name: str, key: str, location: Literal["header", "cookie"], **kwargs):
        super().__init__(name, "apiKey", **kwargs)
        self.key = key
        self.location = location

    # TODO: move to OpenAPI
    @property
    def json(self):
        """JSON representation of the security scheme."""
        result = super().json
        result["name"] = self.key
        result["in"] = self.location
        return result

    async def authenticate(value):
        """
        Perform authentication of API key value supplied in the HTTP request. If
        authentication is successful, a context is returned to be pushed on the context stack.
        If authentication fails, None is returned. This method should not raise an exception
        unless an unrecoverable error occurs.
        """
        raise NotImplementedError


class HeaderSecurityScheme(APIKeySecurityScheme):
    """
    Base class for header authentication security scheme. Subclass must implement the
    authenticate method.

    Parameters:
    • name: name of the security scheme
    • header: name of the header to be used
    • description: a short description for the security scheme
    """

    def __init__(self, name: str, header: str, **kwargs):
        super().__init__(name, location="header", key=header, **kwargs)

    async def filter(self, request):
        """
        Filters the incoming HTTP request. If the request contains the header, it is passed to
        the authenticate method. If authentication is successful, a context is added to the
        context stack.
        """
        header = request.headers.get(self.key)
        auth = await self.authenticate(header) if header is not None else None
        with fondat.context.push(auth) if auth else contextlib.nullcontext():
            yield

    async def authenticate(self, header):
        raise NotImplementedError


class CookieSecurityScheme(APIKeySecurityScheme):
    """
    Base class for cookie authentication security scheme. Subclass must implement the
    authenticate method.

    Parameters:
    • name: name of the security scheme
    • cookie: name of cookie to be used
    • description: a short description for the security scheme
    """

    def __init__(self, name: str, cookie: str, **kwargs):
        super().__init__(name, location="cookie", key=cookie, **kwargs)

    async def filter(self, request):
        """
        Filters the incoming HTTP request. If the request contains the cookie, it is passed to
        the authenticate method. If authentication is successful, a context is added to the
        context stack.
        """
        cookie = request.cookies.get(self.key)
        auth = await self.authenticate(cookie) if cookie is not None else None
        with fondat.context.push(auth) if auth else contextlib.nullcontext():
            yield

    async def authenticate(self, cookie):
        raise NotImplementedError


async def _subordinate(resource, segment):

    # resource.attr
    if (attr := getattr(resource, segment, None)) is not None:
        if fondat.resource.is_resource(attr):
            return attr
        if not callable(attr):
            raise fondat.error.NotFoundError
        hints = typing.get_type_hints(attr)
        if not fondat.resource.is_resource(hints.get("return")):
            raise fondat.error.NotFoundError
        if is_coroutine_function(attr):
            return await attr()
        else:
            return attr()

    # resource[item]
    try:
        item = resource[segment]
    except TypeError:
        raise fondat.error.NotFoundError
    if not fondat.resource.is_resource(item):
        raise fondat.error.NotFoundError
    return item


class ParamIn:
    """Base class for parameter annotations."""


class _InString(ParamIn):
    def __init__(
        self, attr: Literal["query", "headers", "cookies"], key: str, description: str
    ):
        super().__init__()
        self.attr = attr
        self.key = key
        self.description = description

    async def get(self, hint, request):
        value = getattr(request, self.attr).get(self.key)
        if value is None:
            return None
        try:
            if is_subclass(hint, Stream):
                return BytesStream(get_codec(String, bytes).decode(value))
            return get_codec(String, hint).decode(value)
        except (TypeError, ValueError) as e:
            raise fondat.error.BadRequestError(f"{e} in {self}")

    def __str__(self):
        return f"{self.description}: {self.key}"


class InQuery(_InString):
    """Annotation to indicate a parameter is provided in request query string."""

    def __init__(self, name: str):
        super().__init__("query", name, "query parameter")


class InHeader(_InString):
    """Annotation to indicate a parameter is provided in request header."""

    def __init__(self, name: str):
        super().__init__("headers", name, "request header")


class InCookie(_InString):
    """Annotation to indicate a parameter is provided in request cookie."""

    def __init__(self, name: str):
        super().__init__("cookies", name, "request cookie")


class _InBody(ParamIn):
    """Annotation to indicate a parameter is provided in request body."""

    async def get(self, hint, request):
        if is_subclass(hint, Stream):
            return request.body
        try:
            value = bytearray()
            if request.body is not None:
                async for b in request.body:
                    value.extend(b)
            if len(value) == 0:  # empty body is no body
                return None
            return get_codec(Binary, hint).decode(value)
        except (TypeError, ValueError) as e:
            raise fondat.error.BadRequestError(f"{e} in {self}")

    def __call__(self):
        return self

    def __str__(self):
        return "request body"


InBody = _InBody()


async def handle_error(err: fondat.error.Error):
    """Default error handler for HTTP application."""

    body = json.dumps(
        dict(error=err.status, detail=err.args[0] if err.args else err.__doc__)
    ).encode()

    response = Response()
    response.status = err.status
    response.headers["content-type"] = "application/json"
    response.headers["content-length"] = str(len(body))
    response.body = BytesStream(body)
    return response


#  TODO: In docstring, add description of routing through resource(s) to an operation.


class Application:
    """
    An HTTP application, which handles ncoming HTTP requests by:
    • passing request through zero or more HTTP filters, and
    • dispatching it to a resource.

    Parameters and attributes:
    • root: resource to dispatch requests to
    • filters: filters to apply during HTTP request processing
    • error_handler: coroutine function to produce response for raised fondat.error exception
    • path: URI path to root resource

    An HTTP application is a request handler; it's a coroutine callable that handles an HTTP
    request and returns an HTTP response.

    For a description of filters, see: Chain.
    """

    def __init__(
        self,
        root: type,
        *,
        filters: Iterable[Any] = None,
        error_handler: Callable = handle_error,
        path: str = "/",
    ):
        if not fondat.resource.is_resource(root):
            raise TypeError("root is not a resource")
        self.root = root
        self.path = path.rstrip("/") + "/"
        self.filters = list(filters or [])
        self.error_handler = error_handler

    async def __call__(self, *args, **kwargs):
        return await self.handle(*args, **kwargs)

    async def handle(self, request: Request):
        try:
            try:
                chain = Chain(filters=self.filters, handler=self._handle)
                return await chain.handle(request)
            except fondat.error.Error:
                raise
            except Exception as ex:
                raise fondat.error.InternalServerError from ex
        except fondat.error.Error as err:
            if isinstance(err, fondat.error.InternalServerError):
                _logger.error(msg=err.__cause__.args[0], exc_info=err.__cause__, stacklevel=3)
            return await self.error_handler(err)

    async def _handle(self, request: Request):
        if not request.path.startswith(self.path):
            raise fondat.error.NotFoundError
        request.path = request.path[len(self.path) :]
        response = Response()
        method = request.method.lower()
        segments = request.path.split("/") if request.path else ()
        resource = self.root
        operation = None
        for segment in segments:
            resource = await _subordinate(resource, segment)
        operation = getattr(resource, method, None)
        if not fondat.resource.is_operation(operation):
            raise fondat.error.MethodNotAllowedError
        signature = inspect.signature(operation)
        params = {}
        hints = typing.get_type_hints(operation, include_extras=True)
        return_hint = hints.get("return", type(None))
        for name, hint in hints.items():
            if name == "return":
                continue
            in_param = None
            if typing.get_origin(hint) is Annotated:
                args = typing.get_args(hint)
                hint = args[0]
                for ann in args[1:]:
                    if isinstance(ann, ParamIn):
                        in_param = ann
                        break
            if not in_param:
                in_param = InQuery(name)
            param = await in_param.get(hint, request)
            if param is None:
                if signature.parameters[
                    name
                ].default is inspect.Parameter.empty and not is_optional(hint):
                    raise fondat.error.BadRequestError(f"expecting value in {in_param}")
                params[name] = None
            else:
                try:
                    validate(param, hint)
                except (TypeError, ValueError) as tve:
                    raise fondat.error.BadRequestError(f"{tve} in {in_param}")
                params[name] = param
        result = await operation(**params)
        validate(result, return_hint)
        if not is_subclass(return_hint, Stream):
            return_codec = get_codec(Binary, return_hint)
            result = BytesStream(return_codec.encode(result), return_codec.content_type)
        response.body = result
        response.headers["Content-Type"] = response.body.content_type
        if response.body.content_length is not None:
            if response.body.content_length == 0:
                response.status = http.HTTPStatus.NO_CONTENT.value
            else:
                response.headers["Content-Length"] = str(response.body.content_length)
        return response
