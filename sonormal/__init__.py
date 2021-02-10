import os
import logging
import flask
import json
from . import utils
from . import normalize
from . import jldextract

def create_app(test_config=None):
    app = flask.Flask(__name__, instance_relative_config=True)
    if test_config == None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    options = {}
    app.register_blueprint(jldextract.jldex, url_prefix="/jldex", **options)

    @app.template_filter()
    def datetimeToJsonStr(dt):
        return utils.datetimeToJsonStr(dt)

    @app.template_filter()
    def asjson(jobj):
        if jobj is not None:
            return json.dumps(jobj, indent=2)
        return ""


    @app.route('/')
    def normalize_so():
        source_url = flask.request.args.get("url", None)
        if source_url is not None:
            if not source_url.startswith('http'):
                flask.abort(404)
            logging.debug("URL = %s", source_url)
            normalizer = normalize.SoNormalize()
            jsonld, http_response = normalize.downloadJson(source_url)
            jsonld_normalized, _, _, _ = normalizer.normalizeSchemaOrg(jsonld)
            response = app.response_class(
                response=json.dumps(jsonld_normalized, indent=2),
                mimetype='application/ld+json'
            )
            return response
        return flask.render_template("index.html")

    return app