from flask import Flask

import config
from core import errors, server
from modules.builder import routes as builder
from modules.companion import routes as companion
from modules.conversion import queue as conversion
from modules.documents import routes as documents
from modules.home import routes as home
from modules.library import routes as library
from modules.profiles import routes as profiles
from modules.reread import routes as reread
from modules.upload import routes as upload


def create_app():
    app = Flask(__name__, static_folder=str(config.STATIC_DIR), template_folder=str(config.TEMPLATE_DIR))
    app.config["MAX_CONTENT_LENGTH"] = config.REQUEST_MAX_BYTES
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    errors.register(app)
    for module in (companion, home, documents, upload, builder, reread, profiles, library):
        app.register_blueprint(module.bp)
    return app


app = create_app()

if __name__ == "__main__":
    server.run(app, on_start=[conversion.resume_pending])
