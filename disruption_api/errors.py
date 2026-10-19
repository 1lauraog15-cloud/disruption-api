"""Uniform JSON errors and response headers, so nothing leaks stack traces or HTML pages."""

import logging
import re

from flask import Flask, Response, jsonify, request
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def register_http_hardening(app: Flask) -> None:
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

    @app.errorhandler(HTTPException)
    def handle_http(exc: HTTPException) -> Response:
        response = jsonify({"error": _slug(exc.name), "message": exc.description})
        response.status_code = exc.code or 500
        for key, value in exc.get_headers():
            if key.lower() not in {"content-type", "content-length"}:
                response.headers[key] = value  # e.g. Allow on 405
        return response

    @app.errorhandler(IntegrityError)
    def handle_integrity(_exc: IntegrityError) -> tuple[Response, int]:
        # A constraint was violated, typically a duplicate created by a concurrent request.
        return jsonify({"error": "conflict", "message": "the resource conflicts with existing data"}), 409

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception) -> tuple[Response, int]:
        log.exception("unhandled error on %s %s", request.method, request.path, exc_info=exc)
        return jsonify({"error": "internal_error", "message": "unexpected error"}), 500

    @app.after_request
    def add_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if response.mimetype == "application/json":
            response.headers.setdefault("Cache-Control", "no-store")
        return response
