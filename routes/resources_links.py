import os
from flask import (
    Blueprint,
    render_template,
    send_from_directory,
    current_app,
    request,
    redirect,
    url_for,
    flash
)
from flask_login import login_required
from werkzeug.utils import secure_filename

resources_links_bp = Blueprint('resources_links', __name__)

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'csv', 'xlsx'}


def allowed_file(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@resources_links_bp.route('/resources-links')
@login_required
def index():
    files = []

    folder = current_app.config['RESOURCES_FOLDER']

    os.makedirs(folder, exist_ok=True)

    for f in os.listdir(folder):
        path = os.path.join(folder, f)

        if os.path.isfile(path):
            size_mb = os.path.getsize(path) / (1024 * 1024)

            files.append({
                'name': f,
                'size': f"{round(size_mb, 2)} MB",
                'ext': f.rsplit('.', 1)[-1].upper()
            })

    return render_template(
        'resources_links.html',
        uploaded_files=files
    )


@resources_links_bp.route('/api/resources/upload', methods=['POST'])
@login_required
def upload_file():

    if 'file' not in request.files:
        flash('No file part.', 'danger')
        return redirect(url_for('resources_links.index'))

    file = request.files['file']

    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('resources_links.index'))

    if not allowed_file(file.filename):
        flash(
            'Invalid file type. Only PDF, DOCX, CSV and XLSX files are allowed.',
            'danger'
        )
        return redirect(url_for('resources_links.index'))

    filename = secure_filename(file.filename)

    if not filename:
        flash('Invalid filename.', 'danger')
        return redirect(url_for('resources_links.index'))

    folder = current_app.config['RESOURCES_FOLDER']
    os.makedirs(folder, exist_ok=True)

    save_path = os.path.join(folder, filename)

    file.save(save_path)

    flash(
        f'File "{filename}" uploaded successfully to resources catalog.',
        'success'
    )

    return redirect(url_for('resources_links.index'))


@resources_links_bp.route('/downloads/resources/<filename>')
@login_required
def download_file(filename):

    safe_filename = secure_filename(filename)

    return send_from_directory(
        current_app.config['RESOURCES_FOLDER'],
        safe_filename
    )