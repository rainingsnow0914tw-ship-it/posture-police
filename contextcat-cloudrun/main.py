"""
ContextCat Media Generation Service
Cloud Run service that bridges GitLab Duo Flow with Google Vertex AI

Flow:
1. GitLab Webhook triggers this service when Issue is updated
2. Service reads storyboard JSON from Issue comment
3. Calls Imagen 3 to generate reference images
4. Calls Veo 3 to generate video clips with audio
5. Writes results back to GitLab Issue

Author: Chloe Kao × Claude (Anthropic)
License: MIT
"""

import os
import json
import re
import time
import logging
import requests
from flask import Flask, request, jsonify
import google.auth
import google.auth.transport.requests
from google.oauth2 import service_account

# ─── Logging setup ────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ─── Config from environment variables ────────────────────────
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# ─── Google Auth helper ────────────────────────────────────────
def get_google_token():
    """Get Google access token for Vertex AI API calls."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token


# ═══════════════════════════════════════════════════════════════
# GITLAB HELPERS
# ═══════════════════════════════════════════════════════════════

def get_issue(project_id: int, issue_iid: int) -> dict:
    """Read a GitLab Issue and all its comments."""
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    
    # Get issue body
    issue_url = f"{GITLAB_URL}/api/v4/projects/{project_id}/issues/{issue_iid}"
    issue_resp = requests.get(issue_url, headers=headers, timeout=30)
    issue_resp.raise_for_status()
    issue = issue_resp.json()
    
    # Get all comments (notes)
    notes_url = f"{GITLAB_URL}/api/v4/projects/{project_id}/issues/{issue_iid}/notes"
    notes_resp = requests.get(notes_url, headers=headers, params={"per_page": 100}, timeout=30)
    notes_resp.raise_for_status()
    
    issue["notes"] = notes_resp.json()
    return issue


def post_issue_comment(project_id: int, issue_iid: int, body: str):
    """Post a comment to a GitLab Issue."""
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN, "Content-Type": "application/json"}
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/issues/{issue_iid}/notes"
    resp = requests.post(url, headers=headers, json={"body": body}, timeout=30)
    resp.raise_for_status()
    logger.info(f"Posted comment to Issue #{issue_iid}")
    return resp.json()


def extract_storyboard_json(issue: dict) -> dict | None:
    """
    Find the most recent ```storyboard JSON block in Issue comments.
    Cat-2 posts its output in this format.
    """
    # Search notes in reverse order (most recent first)
    notes = sorted(issue.get("notes", []), key=lambda n: n["created_at"], reverse=True)
    
    for note in notes:
        body = note.get("body", "")
        # Look for ```storyboard code block
        match = re.search(r"```storyboard\s*\n(.*?)\n```", body, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse storyboard JSON: {e}")
                continue
    
    # Also check issue body
    body = issue.get("description", "")
    match = re.search(r"```storyboard\s*\n(.*?)\n```", body, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    return None


# ═══════════════════════════════════════════════════════════════
# STORY BIBLE BUILDER
# ═══════════════════════════════════════════════════════════════

def build_story_bible(clips: list[dict], project_context: str = "") -> str:
    """
    Build a Story Bible from all visual blocks combined.
    This ensures visual consistency across all Imagen 3 calls.
    
    The Story Bible is prepended to every Imagen 3 prompt
    so all images share the same character, palette, and world.
    """
    # Collect all visual descriptions
    all_visuals = [clip.get("visual", "") for clip in clips]
    
    # Use Claude via simple heuristics to extract consistent elements
    # (In production, this could call Claude API for better extraction)
    story_bible_parts = []
    
    # Extract common visual elements
    # Look for character descriptions
    char_mentions = []
    for v in all_visuals:
        words = v.lower()
        if any(word in words for word in ["woman", "man", "person", "character"]):
            char_mentions.append(v[:80])
    
    if char_mentions:
        story_bible_parts.append(f"CHARACTER: {char_mentions[0]}")
    
    # Add style context
    if project_context:
        story_bible_parts.append(f"VISUAL STYLE: {project_context}")
    
    # Add consistency instruction
    story_bible_parts.append(
        "CONSISTENCY: Same character appearance, same color palette, "
        "same lighting style across all frames. Cinematic quality."
    )
    
    story_bible = " | ".join(story_bible_parts)
    logger.info(f"Story Bible built: {story_bible[:100]}...")
    return story_bible


# ═══════════════════════════════════════════════════════════════
# IMAGEN 3: REFERENCE IMAGE GENERATION
# ═══════════════════════════════════════════════════════════════

def generate_reference_image(visual_prompt: str, story_bible: str, clip_id: int) -> str | None:
    """
    Generate a reference image using Imagen 3 via Vertex AI.
    Returns the GCS URI of the generated image.
    
    The story_bible is prepended to ensure visual consistency
    across all clips in the same video.
    """
    token = get_google_token()
    
    # Combine story bible with clip-specific visual prompt
    full_prompt = f"{story_bible} | {visual_prompt}"
    
    # Remove any audio-related words that might confuse Imagen 3
    audio_words = ["voiceover", "narration", "says:", "music", "sound", "sfx", "audio"]
    for word in audio_words:
        full_prompt = re.sub(rf'\b{word}\b.*?[,.]', '', full_prompt, flags=re.IGNORECASE)
    
    logger.info(f"Imagen 3 prompt for clip {clip_id}: {full_prompt[:120]}...")
    
    endpoint = (
        f"https://{GCP_LOCATION}-aiplatform.googleapis.com/v1/"
        f"projects/{GCP_PROJECT_ID}/locations/{GCP_LOCATION}/"
        f"publishers/google/models/imagen-3.0-generate-001:predict"
    )
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "instances": [{
            "prompt": full_prompt
        }],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "9:16",
            "safetyFilterLevel": "block_some",
            "personGeneration": "allow_adult"
        }
    }
    
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        result = resp.json()
        
        # Extract image data
        predictions = result.get("predictions", [])
        if predictions and "bytesBase64Encoded" in predictions[0]:
            # Save to GCS or return base64
            # For simplicity, return the base64 data URI
            img_data = predictions[0]["bytesBase64Encoded"]
            logger.info(f"✅ Imagen 3 generated image for clip {clip_id}")
            return f"data:image/png;base64,{img_data}"
        
        logger.warning(f"No image data in Imagen 3 response for clip {clip_id}")
        return None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Imagen 3 API error for clip {clip_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# VEO 3: VIDEO + AUDIO GENERATION
# ═══════════════════════════════════════════════════════════════

def build_veo3_prompt(clip: dict) -> str:
    """
    Build a Veo 3 native format prompt from the clip JSON.
    
    Critical Veo 3 rules:
    - Use "Character says: dialogue" (with colon) to prevent subtitle generation
    - Specify all audio elements explicitly
    - Add negative prompts to reduce common AI errors
    """
    visual = clip.get("visual", "")
    audio = clip.get("audio", {})
    
    voiceover = audio.get("voiceover", "")
    sfx = audio.get("sfx", "")
    music = audio.get("music", "")
    
    parts = [visual]
    
    # Add voiceover with correct syntax (colon prevents subtitle generation)
    if voiceover:
        parts.append(f"A calm voice narrates: {voiceover}")
    
    # Add sound design
    if sfx:
        parts.append(f"Audio: {sfx}.")
    
    if music:
        parts.append(f"Background music: {music}.")
    
    # Add negative prompts to reduce common AI errors
    parts.append(
        "No morphing, no distortion, no text overlays, "
        "no watermarks, no subtitle captions, smooth motion."
    )
    
    return " ".join(parts)


def generate_video_clip(
    clip: dict,
    reference_image_data: str | None,
    clip_id: int
) -> str | None:
    """
    Generate a video clip with native audio using Veo 3.
    Returns the GCS URI of the generated video.
    
    Uses Veo 3's predictLongRunning endpoint because video
    generation takes 60-120 seconds.
    """
    token = get_google_token()
    
    veo3_prompt = build_veo3_prompt(clip)
    logger.info(f"Veo 3 prompt for clip {clip_id}: {veo3_prompt[:120]}...")
    
    endpoint = (
        f"https://{GCP_LOCATION}-aiplatform.googleapis.com/v1/"
        f"projects/{GCP_PROJECT_ID}/locations/{GCP_LOCATION}/"
        f"publishers/google/models/veo-3.0-generate-preview:predictLongRunning"
    )
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Build instance with optional reference image
    instance = {"prompt": veo3_prompt}
    if reference_image_data:
        instance["image"] = {"bytesBase64Encoded": reference_image_data.split(",")[1]}
    
    payload = {
        "instances": [instance],
        "parameters": {
            "aspectRatio": "9:16",
            "sampleCount": 1,
            "durationSeconds": clip.get("duration", 8),
            "enhancePrompt": True,
            "generateAudio": True,
            "storageUri": f"gs://{GCP_PROJECT_ID}-contextcat-output/"
        }
    }
    
    try:
        # Start long-running operation
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        operation = resp.json()
        operation_name = operation.get("name", "")
        
        if not operation_name:
            logger.error(f"No operation name returned for clip {clip_id}")
            return None
        
        logger.info(f"Veo 3 operation started for clip {clip_id}: {operation_name}")
        
        # Poll for completion (max 10 minutes)
        return poll_veo3_operation(operation_name, clip_id)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Veo 3 API error for clip {clip_id}: {e}")
        return None


def poll_veo3_operation(operation_name: str, clip_id: int, max_wait: int = 600) -> str | None:
    """
    Poll the long-running Veo 3 operation until it completes.
    Checks every 15 seconds, up to max_wait seconds.
    """
    token = get_google_token()
    
    op_endpoint = (
        f"https://{GCP_LOCATION}-aiplatform.googleapis.com/v1/{operation_name}"
    )
    
    headers = {"Authorization": f"Bearer {token}"}
    elapsed = 0
    
    while elapsed < max_wait:
        time.sleep(15)
        elapsed += 15
        
        # Refresh token every 5 minutes
        if elapsed % 300 == 0:
            token = get_google_token()
            headers["Authorization"] = f"Bearer {token}"
        
        try:
            resp = requests.get(op_endpoint, headers=headers, timeout=30)
            resp.raise_for_status()
            op = resp.json()
            
            if op.get("done"):
                if "error" in op:
                    logger.error(f"Veo 3 operation failed for clip {clip_id}: {op['error']}")
                    return None
                
                # Extract video URI from response
                response = op.get("response", {})
                predictions = response.get("predictions", [])
                if predictions:
                    video_uri = predictions[0].get("gcsUri", "")
                    if video_uri:
                        logger.info(f"✅ Veo 3 generated video for clip {clip_id}: {video_uri}")
                        return video_uri
            
            logger.info(f"Clip {clip_id}: waiting... ({elapsed}s elapsed)")
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Poll error for clip {clip_id}: {e}")
    
    logger.error(f"Veo 3 operation timed out for clip {clip_id}")
    return None


# ═══════════════════════════════════════════════════════════════
# MAIN PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def run_media_pipeline(project_id: int, issue_iid: int):
    """
    Main pipeline that:
    1. Reads storyboard from GitLab Issue
    2. Generates reference images with Imagen 3
    3. Generates video clips with Veo 3
    4. Posts results back to GitLab Issue
    """
    logger.info(f"Starting ContextCat media pipeline for Issue #{issue_iid}")
    
    # Step 1: Read Issue
    post_issue_comment(
        project_id, issue_iid,
        "☁️ **ContextCat Cloud Run** activated!\n\n"
        "🔄 Reading storyboard from Issue..."
    )
    
    issue = get_issue(project_id, issue_iid)
    storyboard = extract_storyboard_json(issue)
    
    if not storyboard:
        post_issue_comment(
            project_id, issue_iid,
            "❌ **ContextCat Error**: Could not find storyboard JSON in Issue.\n\n"
            "Please make sure Cat-2 has completed and posted a ```storyboard block."
        )
        return
    
    clips = storyboard.get("clips", [])
    video_ai = storyboard.get("video_ai", "Veo 3")
    total_duration = storyboard.get("total_duration", 30)
    
    logger.info(f"Found storyboard: {len(clips)} clips, {total_duration}s, {video_ai}")
    
    # Step 2: Build Story Bible
    post_issue_comment(
        project_id, issue_iid,
        f"📖 Building Story Bible for visual consistency across {len(clips)} clips..."
    )
    
    project_context = issue.get("description", "")
    story_bible = build_story_bible(clips, project_context)
    
    # Step 3: Generate reference images with Imagen 3
    post_issue_comment(
        project_id, issue_iid,
        f"🎨 **Cat-3 (Visual Officer)** generating {len(clips)} reference images with Imagen 3...\n\n"
        "_Using Story Bible to ensure visual consistency_"
    )
    
    reference_images = []
    image_results = []
    
    for i, clip in enumerate(clips):
        clip_id = clip.get("clip_id", i + 1)
        visual = clip.get("visual", "")
        
        logger.info(f"Generating reference image for clip {clip_id}...")
        img_data = generate_reference_image(visual, story_bible, clip_id)
        reference_images.append(img_data)
        
        if img_data:
            image_results.append(f"- Clip {clip_id}: ✅ Generated")
        else:
            image_results.append(f"- Clip {clip_id}: ⚠️ Failed (will proceed without reference)")
    
    # Post Checkpoint 1
    checkpoint_msg = (
        "🎨 **Cat-3 Complete! Reference images generated.**\n\n"
        "**Story Bible:**\n"
        f"```\n{story_bible}\n```\n\n"
        "**Reference images:**\n"
        + "\n".join(image_results) + "\n\n"
        "---\n"
        "🛑 **Human Checkpoint 1 — Review before video generation**\n\n"
        "Do the reference images look right for your project?\n\n"
        f"✅ Reply `@ai-contextcat-part-2-chloe-kao approved, generate videos` to continue\n"
        f"❌ Reply `@ai-contextcat-part-2-chloe-kao start over` to restart"
    )
    post_issue_comment(project_id, issue_iid, checkpoint_msg)
    
    # Wait for human approval (check Issue for approval comment)
    logger.info("Waiting for human approval at Checkpoint 1...")
    approved = wait_for_approval(project_id, issue_iid, keyword="approved, generate videos")
    
    if not approved:
        post_issue_comment(
            project_id, issue_iid,
            "⏸️ **ContextCat paused** — waiting for your approval.\n"
            "Reply with `approved, generate videos` when ready!"
        )
        return
    
    # Step 4: Generate video clips with Veo 3
    post_issue_comment(
        project_id, issue_iid,
        f"🎬 **Cat-4 (Audio Director)** generating {len(clips)} video clips with Veo 3...\n\n"
        "_This may take 2-5 minutes per clip. Sit tight! 🐱_"
    )
    
    video_results = []
    video_urls = []
    
    for i, clip in enumerate(clips):
        clip_id = clip.get("clip_id", i + 1)
        
        post_issue_comment(
            project_id, issue_iid,
            f"🎬 Generating clip {clip_id}/{len(clips)} with Veo 3 (video + audio)..."
        )
        
        video_uri = generate_video_clip(clip, reference_images[i], clip_id)
        video_urls.append(video_uri)
        
        if video_uri:
            video_results.append(f"| {clip_id} | {clip.get('duration', 8)}s | {video_uri} | ✅ |")
        else:
            video_results.append(f"| {clip_id} | {clip.get('duration', 8)}s | Generation failed | ❌ |")
    
    # Step 5: Post final delivery package
    delivery_msg = (
        "🐱 **ContextCat Delivery Complete!**\n\n"
        "## 📦 Your Video Production Package\n\n"
        f"**Format:** {len(clips)} clips × {clips[0].get('duration', 8)}s = {total_duration}s | {video_ai}\n\n"
        "---\n\n"
        "### 🎬 Video Clips (with audio)\n\n"
        "| Clip | Duration | Video URL | Status |\n"
        "|------|----------|-----------|--------|\n"
        + "\n".join(video_results) + "\n\n"
        "### 📖 Story Bible\n"
        f"```\n{story_bible}\n```\n\n"
        "---\n\n"
        "**Next step:** Download clips and import into CapCut to assemble final video. 🎬\n\n"
        "_Generated by ContextCat × Claude (Anthropic) × Imagen 3 × Veo 3 × Google Cloud Run_"
    )
    post_issue_comment(project_id, issue_iid, delivery_msg)
    logger.info(f"✅ ContextCat pipeline complete for Issue #{issue_iid}")


def wait_for_approval(
    project_id: int,
    issue_iid: int,
    keyword: str,
    max_wait: int = 3600
) -> bool:
    """
    Poll the Issue for an approval comment.
    Checks every 30 seconds for up to max_wait seconds (default 1 hour).
    """
    elapsed = 0
    while elapsed < max_wait:
        time.sleep(30)
        elapsed += 30
        
        issue = get_issue(project_id, issue_iid)
        notes = sorted(
            issue.get("notes", []),
            key=lambda n: n["created_at"],
            reverse=True
        )
        
        for note in notes[:5]:  # Check last 5 comments
            body = note.get("body", "").lower()
            if keyword.lower() in body:
                logger.info(f"✅ Approval received after {elapsed}s")
                return True
    
    return False


# ═══════════════════════════════════════════════════════════════
# FLASK WEBHOOK ENDPOINT
# ═══════════════════════════════════════════════════════════════

@app.route("/webhook", methods=["POST"])
def gitlab_webhook():
    """
    Receives GitLab webhook events.
    Triggers when an Issue Note (comment) is created.
    
    Looks for comments containing the trigger phrase:
    "contextcat generate media" or "cat3 start"
    """
    # Verify webhook secret
    token = request.headers.get("X-Gitlab-Token", "")
    if WEBHOOK_SECRET and token != WEBHOOK_SECRET:
        logger.warning("Invalid webhook secret")
        return jsonify({"error": "Unauthorized"}), 401
    
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No payload"}), 400
    
    # Only handle Note (comment) events on Issues
    event_type = payload.get("object_kind")
    if event_type != "note":
        return jsonify({"status": "ignored", "reason": "not a note event"}), 200
    
    noteable_type = payload.get("object_attributes", {}).get("noteable_type")
    if noteable_type != "Issue":
        return jsonify({"status": "ignored", "reason": "not an issue note"}), 200
    
    # Extract Issue details
    project_id = payload.get("project", {}).get("id")
    issue_iid = payload.get("issue", {}).get("iid")
    comment_body = payload.get("object_attributes", {}).get("note", "").lower()
    
    if not project_id or not issue_iid:
        return jsonify({"error": "Missing project_id or issue_iid"}), 400
    
    # Check if this comment should trigger the media pipeline
    trigger_phrases = [
        "contextcat generate media",
        "cat3 start",
        "generate images and videos",
        "start media pipeline"
    ]
    
    should_trigger = any(phrase in comment_body for phrase in trigger_phrases)
    
    # Also trigger if Cat-2 posts storyboard (contains ```storyboard)
    if "```storyboard" in payload.get("object_attributes", {}).get("note", ""):
        should_trigger = True
    
    if not should_trigger:
        return jsonify({"status": "ignored", "reason": "no trigger phrase found"}), 200
    
    logger.info(f"Triggering media pipeline for project {project_id}, issue #{issue_iid}")
    
    # Run pipeline in background (for production, use Cloud Tasks or Pub/Sub)
    # For hackathon demo, run synchronously
    try:
        run_media_pipeline(project_id, issue_iid)
        return jsonify({"status": "success", "message": "Pipeline completed"}), 200
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Cloud Run."""
    return jsonify({
        "status": "healthy",
        "service": "ContextCat Media Generation",
        "version": "1.0.0"
    }), 200


@app.route("/", methods=["GET"])
def index():
    """Root endpoint."""
    return jsonify({
        "service": "ContextCat Cloud Run",
        "description": "AI Video Production Pipeline Bridge",
        "endpoints": {
            "/webhook": "GitLab webhook receiver (POST)",
            "/health": "Health check (GET)"
        }
    }), 200


# ─── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
