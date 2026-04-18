"""
TruthLens — Flask Application Entry Point
Serves the built React SPA and exposes /api/verify.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from backend.verify import verify_content

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------
STATIC_FOLDER = BASE_DIR / "dist"

app = Flask(__name__, static_folder=str(STATIC_FOLDER), static_url_path="")


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------
@app.route("/api/verify", methods=["POST"])
def api_verify():
    try:
        body = request.get_json(force=True, silent=True) or {}
        text = body.get("text", "")
        image_data = body.get("image")  # { data: base64str, mimeType: str } or None

        if not text.strip() and not image_data:
            return jsonify({"error": "Please provide either text or an image to verify."}), 400

        result = verify_content(text, image_data)
        return jsonify(result)

    except (ValueError, PermissionError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        print(f"Unhandled error in /api/verify: {exc}")
        return jsonify({"error": str(exc) or "An unexpected error occurred."}), 500


# ---------------------------------------------------------------------------
# Serve React SPA
# ---------------------------------------------------------------------------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    dist = Path(app.static_folder)
    target = dist / path
    if path and target.exists() and target.is_file():
        return send_from_directory(str(dist), path)
    # Fallback: always serve index.html (React handles routing)
    index = dist / "index.html"
    if index.exists():
        return send_from_directory(str(dist), "index.html")
    return (
        "<h2>React build not found.</h2>"
        "<p>Run <code>npm run build</code> in the project root first, then restart Flask.</p>",
        404,
    )


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() in ("1", "true", "yes")
    print(f"\nTruthLens Flask server starting on http://localhost:{port}\n")
    app.run(debug=debug, port=port)
