# 🐱 ContextCat

> **AI Memory & Multi-Agent Orchestration for GitLab Duo**

[![GitLab Duo Agent Platform](https://img.shields.io/badge/GitLab%20Duo-Agent%20Platform-FC6D26?style=for-the-badge&logo=gitlab)](https://about.gitlab.com/gitlab-duo/agent-platform/)
[![Powered by Claude](https://img.shields.io/badge/Powered%20by-Claude%20(Anthropic)-6B46C1?style=for-the-badge)](https://www.anthropic.com/claude)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

---

## The Problem: The AI Amnesia Loop

Every developer using AI tools in Chat mode faces the same painful cycle:

```
Open new chat → Re-explain entire project background (5 min)
→ Generate output → Copy → Open new window → Paste → Copy result
→ Open another window → Paste again → Wait → Repeat
→ 45 minutes later: sore eyes, exhausted hands, 9 windows open
```

Three pain points that slow every AI-augmented team:

| Pain | Reality |
|------|---------|
| 🧠 **AI Amnesia** | Every new chat window = start from zero |
| 🔗 **Human Relay** | You manually copy outputs between AI tools |
| ⏱️ **Serial Queue** | Tasks run one by one, no parallel work |

---

## The Solution: ContextCat

ContextCat is a **GitLab Duo Agent Flow** powered by Claude (Anthropic).

It acts as a **persistent memory layer and AI orchestrator** — triggered by a single `@mention`, it wakes up six specialized agents, coordinates their work, and delivers a complete output package stored in GitLab Issues forever.

```
You type:  @ai-contextcat-part-1-chloe-kao make me a MoodBloom 30-sec Veo 3 video package

ContextCat does the rest. 3 minutes later, everything is in the Issue.
```

---

## How It Works: Six Cats, One Pipeline

```
@mention trigger
      ↓
🐱 Cat-1 (Memory Officer / Claude)
   Reads GitLab Issue memory → Checks if context is sufficient
   → Asks ONLY for what's missing
      ↓
🐱 Cat-2 (Storyboard Officer / Claude)
   Calculates clip count → Generates structured JSON prompts
   {visual block for Imagen 3} + {audio block for Veo 3}
      ↓
🐱 Cat-3 (Visual Officer / Gemini + Imagen 3)
   Reads ALL visual blocks → Builds Story Bible (consistency!)
   → Generates 4 reference images with unified character/style
      ↓
🛑 HUMAN CHECKPOINT 1 — Review reference images (free, no risk)
   ✅ Approve → ✏️ Modify → ❌ Start over
      ↓
🐱 Cat-4 (Audio Director / Gemini + Veo 3)
   Full JSON + reference image → Veo 3 native format
   → Generates video clip WITH voiceover + SFX + music
      ↓
🐱 Cat-4.5 (QC Inspector / Claude)
   Checks first + last frame of each clip
   → Catches: extra fingers, wrong phone orientation, physics violations
   → Silent pass OR pause + alert user
      ↓
🛑 HUMAN CHECKPOINT 2 — Review all video clips
   ✅ Package it → ✏️ Redo specific clip → ❌ Start over
      ↓
🐱 Cat-5 (Packaging Officer / Claude)
   Collects all outputs → Writes to GitLab Issue
   → Notifies in Chat: "✅ Complete! Everything in Issue #42"
```

---

## Key Design Decisions

### Why Structured JSON Prompts?

```json
{
  "clip_1": {
    "visual": "Woman, 30s, warm desk, soft lamp — pure visual, NO audio",
    "audio": {
      "voiceover": "Today I finally let it go...",
      "sfx": "ambient cafe, rain on window",
      "music": "soft piano, melancholic, slow tempo"
    }
  }
}
```

**The problem this solves:** If you give Imagen 3 a prompt containing voiceover text, it draws the text on the image. By splitting into `visual` and `audio` blocks from the same source, both tools get exactly what they need — no conflicts.

### Why Gemini Builds a Story Bible Before Generating Images?

Direct approach (wrong):
```
Prompt 1 → Imagen 3 → Image A (character has black hair)
Prompt 2 → Imagen 3 → Image B (character has blonde hair)
Prompt 3 → Imagen 3 → Image C (completely different style)
Result: 3 videos that look like different films 💀
```

ContextCat approach (correct):
```
All 4 prompts → Gemini reads the whole story
Gemini builds Story Bible: character, palette, lighting, mood arc
Gemini calls Imagen 3 × 4 with consistent world context
Result: 4 images that belong to the same story ✅
```

### Why Two Human Checkpoints?

| Gate | When | Why |
|------|------|-----|
| 🛑 Gate 1 | After reference images | Images are free. Fix visual direction NOW before spending on Veo 3. |
| 🛑 Gate 2 | After all video clips | Confirm quality before packaging and archiving. |
| 🤖 Cat-4.5 | After EACH clip (auto) | Catches AI errors silently. Only interrupts if something is wrong. |

---

## Before vs After

| | Without ContextCat | With ContextCat |
|--|--|--|
| **Time** | 45 minutes | 3 minutes |
| **Windows open** | 9 chat windows | 1 GitLab Issue |
| **Context re-explained** | Every single time | Never again |
| **Visual consistency** | Hope for the best | Story Bible guarantees it |
| **Quality control** | Manual review of everything | Cat-4.5 auto-checks frames |
| **Memory** | Lost when you close the tab | Lives in GitLab Issue forever |

---

## Technology Stack

| Component | Technology | Role |
|-----------|-----------|------|
| Orchestration | GitLab Duo Agent Platform | Flow engine + trigger system |
| Cat-1, 2, 4.5, 5 | Claude (Anthropic) | Memory, storyboard, QC, packaging |
| Cat-3 | Gemini + Imagen 3 | Story Bible + reference images |
| Cat-4 | Gemini + Veo 3 | Video + voiceover + SFX + music |
| Memory Store | GitLab Issues | Persistent cross-session context |
| Trigger | @mention in GitLab Chat | Natural language, zero UI learning |
| Network | agent-config.yml policy | Allows googleapis.com for Veo 3 / Imagen 3 |

---

## Project Structure

```
contextcat/
├── README.md                          # This file
├── LICENSE                            # MIT License
├── .gitlab/
│   └── duo/
│       ├── flows/
│       │   ├── contextcat_part1.yaml  # Cat-1 + Cat-2 (Memory + Storyboard)
│       │   └── contextcat_part2.yaml  # Cat-3,4,4.5,5 (Visual + Video + QC + Package)
│       └── agent-config.yml           # Network policy for external APIs
├── docs/
│   ├── PRD_v2.0.md                    # Full product requirements
│   ├── architecture.md               # Six cats architecture deep dive
│   └── demo_script.md                # Demo video script
└── examples/
    ├── sample_memory_issue.md         # Example GitLab Issue with ContextCat Memory
    └── sample_storyboard_output.json  # Example Cat-2 JSON output
```

---

## How to Use ContextCat

### Step 1: Set up your memory Issue

Create a GitLab Issue with this template:

```markdown
## ContextCat Memory

- **Project name**: [Your project name]
- **Description**: [What your app/product does in 1-2 sentences]
- **Target audience**: [Who it's for]
- **Visual style**: [e.g. warm and cosy, minimalist, energetic]
- **Mood**: [e.g. healing, professional, playful]
- **Brand colours**: [e.g. soft purple #9B8EC4]
- **Character**: [e.g. young woman, late 20s, natural look — or "no character"]
- **Text overlay**: [Yes/No — should text appear in the video?]
```

### Step 2: Enable the Flow in your project

1. Go to **Automate → Flows** in your GitLab project
2. Find **ContextCat Part 1** → Click **Enable**
3. Select your group and project
4. Choose trigger: **Mention**

### Step 3: Trigger ContextCat

In your memory Issue, add a comment:

```
@ai-contextcat-part-1-[your-group] make me a [project] 30-sec Veo 3 video package
```

### Step 4: Follow the cats

ContextCat will:
1. Read your memory Issue
2. Ask for any missing information
3. Generate storyboard prompts
4. Show you reference images for approval
5. Generate video clips with sound
6. Package everything back in your Issue

---

## Hackathon Context

**GitLab AI Hackathon 2026**

ContextCat targets multiple prize tracks:

| Prize | Amount | Our Angle |
|-------|--------|-----------|
| Grand Prize | $15,000 | Creative + technical + impactful |
| Anthropic + GitLab | $10,000 | Claude powers 4 of 6 cats natively |
| Most Impactful | $5,000 | Solves universal AI-era pain |
| Easiest to Use | $5,000 | One @mention, zero config |

---

## Built With ❤️ By

**Chloe Kao** (AI Orchestrator & Product Lead)
× **Claude 阿寶** (Architecture & Core Brain / Anthropic)
× **Gemini Jimmy** (Visual Engine / Google)
× **Veo 3** (Video Generation / Google DeepMind)

> *"ContextCat is not just a hackathon project.*
> *It is the tool we needed while building every hackathon project before this one."*

---

## License

MIT License — see [LICENSE](LICENSE) for details.

All YAML configuration files are original work by the authors.
Third-party APIs (Google Gemini, Imagen 3, Veo 3) used under their respective terms of service.