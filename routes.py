from datetime import datetime
import uuid

from flask import (
    request,
    Blueprint,
    render_template,
    jsonify,
    redirect,
    Response,
    flash,
)
from models import Source, Snippet, User, SyncRecord, Device
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, login_user, logout_user, current_user

from services import source_processors

main = Blueprint("main", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


@main.get("/register")
def register():
    return render_template("register.html")


@main.get("/login")
def login():
    return render_template("login.html")


@main.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


@main.get("/")
@login_required
def index():
    sources = Source.get_user_sources_snippets(current_user.id)
    return render_template("index.html", sources=sources)


@main.post("/login")
def login_post():
    if request.form:
        username = request.form["email"]
        password = request.form["password"]
        user = User.find_by_email(username)
        if user and check_password_hash(user.password, password):
            login_user(user)
            response = Response("Logged in", 200)
            response.headers["HX-Redirect"] = "/"
            return response
    return render_template(
        "partials/login_form.html", message="Invalid credentials.", style="danger"
    )


@main.post("/register")
def register_user():
    password = request.form["password"]
    password_confirmation = request.form["confirm_password"]
    if password != password_confirmation:
        return render_template(
            "partials/register_form.html",
            message="Passwords do not match.",
            style="danger",
        )
    email = request.form["email"]
    password_hash = generate_password_hash(password)

    user = User.find_by_email(email)
    if user:
        return render_template(
            "partials/register_form.html",
            message="User already exists.",
            style="danger",
        )

    User.create(email, password_hash)
    flash("User created. Please login.", "success")
    response = Response("success", 200)
    response.headers["HX-Redirect"] = "/login"
    return response


# TODO: Move this to a service
def get_markdown(source_id, user_id, exclusions=[], latest=False):
    since = datetime.min
    if latest and (sync_record := SyncRecord.get_user_sync_record(source_id, user_id)):
        since = sync_record.synced_at
    source = Source.find_by_id(source_id)
    snippets = Snippet.get_snippets_since(source_id, since)

    markdown = ""
    if "title" not in exclusions:
        markdown = f"# {source.title}\n\n"
        markdown += f"[{source.title}]({source.url})\n\n"
    if "thumbnail" not in exclusions:
        markdown += f"![thumbnail]({source.thumb_url})\n\n"
    for snippet in snippets:
        markdown += f"{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n"

    return markdown


@main.get("/source/<int:source_id>/markdown")
@login_required
def get_source_markdown(source_id):
    user_id = current_user.id
    return get_markdown(source_id, user_id)


@main.delete("/source/<int:source_id>")
def delete_source(source_id):
    source = Source.find_by_id(source_id)
    snippets = source.snippets
    for snippet in snippets:
        snippet.delete_from_db()
    source.delete_from_db()
    return ""


@main.post("/snippets")
def create_snippet():
    sources = []
    url = request.form.get("url")
    duration = request.form.get("duration", 60, type=int)
    time = request.form.get("time", 0)
    if current_user and current_user.is_authenticated:
        source_processors.process_url(url, current_user.id, time, duration)
        sources = Source.get_user_sources_snippets(current_user.id)
        return render_template("partials/sources.html", sources=sources)
    else:
        return "Not authenticated"


@main.post("/snippet/enqueue")
def enqueue_snippet():
    url = request.args.get("url")
    duration = request.args.get("duration", 60, type=int)
    time = request.args.get("time", 0)
    user_id = 1
    source_processors.add_to_queue(url, user_id, time, duration)
    return f"Added {url} to queue", 200


@main.put("/snippet/<int:snippet_id>")
def update_snippet(snippet_id):
    text = request.form.get("text")
    snippet = Snippet.find_by_id(snippet_id)
    snippet.update_text_in_db(text)
    return text


@main.delete("/snippet/<int:snippet_id>")
def delete_snippet(snippet_id):
    snippet = Snippet.find_by_id(snippet_id)
    snippet.delete_from_db()
    return ""


@main.get("/devices")
@login_required
def get_devices():
    if current_user and current_user.is_authenticated:
        user_id = current_user.id

    devices = Device.find_devices_for_user(user_id)
    return render_template("devices.html", devices=devices)


@main.post("/devices")
def add_device():
    if request.form:
        name = request.form.get("device_name")
    if Device.find_by_name(name):
        return "Device already exists", 400

    if current_user and current_user.is_authenticated:
        device_key = uuid.uuid4().hex
        new_device = Device(
            device_name=name, user_id=current_user.id, device_key=device_key
        )
        new_device.add_to_db()

    devices = Device.find_devices_for_user(current_user.id)
    return render_template("partials/device_table.html", devices=devices)


@main.delete("/devices/<int:device_id>")
def delete_device(device_id):
    device = Device.find_by_id(device_id)
    device.delete_from_db()
    return ""


# API BLUEPRINT


@api.get("/source/<int:source_id>/markdown")
def api_get_source_markdown(source_id):
    api_key = request.headers.get("X-Api-Key")
    user_id = Device.find_by_key(api_key).user_id
    get_latest = request.args.get("latest", default=False, type=bool)
    exclusions = request.args.get("exclude", [])
    return get_markdown(source_id, user_id, latest=get_latest, exclusions=exclusions)


@api.post("/source/<int:source_id>/sync")
def create_sync_record(source_id):
    api_key = request.headers.get("X-Api-Key")
    user_id = Device.find_by_key(api_key).user_id
    sync_record = SyncRecord.find_by_user_source(user_id, source_id)
    if sync_record:
        sync_record.update_sync_time()
    else:
        sync_record = SyncRecord(user_id=user_id, source_id=source_id)
        sync_record.add_to_db()
    return jsonify(sync_record)


@api.get("/sources")
def get_sources():
    # TODO Better parsing of args -- failure states
    api_key = request.headers.get("X-Api-Key")
    user_id = Device.find_by_key(api_key).user_id
    sources = Source.get_user_sources_snippets(user_id)
    return jsonify(sources)
