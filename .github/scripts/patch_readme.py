"""
Injects AppNova_Docs-only sections into a synced README.md:
  1. SVG architecture embed  — inserted after the first --- separator
  2. Related docs footer     — appended at the end
Run from the repo root: python3 .github/scripts/patch_readme.py
"""

SVG_BLOCK = (
    "\n"
    "## Frontend Architecture at a Glance\n"
    "\n"
    "![AppNova React Frontend - layered architecture infographic](AppNova_Frontend_Architecture.svg)\n"
    "\n"
    "> Full interactive version: "
    "[AppNova_Frontend_Architecture.html](AppNova_Frontend_Architecture.html) "
    "- Raw SVG: [AppNova_Frontend_Architecture.svg](AppNova_Frontend_Architecture.svg)\n"
    "\n"
    "---\n"
)

RELATED_DOCS_BLOCK = (
    "\n"
    "---\n"
    "\n"
    "## Related docs\n"
    "\n"
    "- [changes.md](changes.md) - Full reverse-chronological change log\n"
    "- [AppNova_Architecture.html](AppNova_Architecture.html) - Interactive architecture overview\n"
    "- [AppNova_Architecture_Diagrams.html](AppNova_Architecture_Diagrams.html) - Mermaid diagram set\n"
    "- [AppNova_Workflow.html](AppNova_Workflow.html) - End-to-end workflow diagram\n"
    "- [AppNova_Complete_Architecture.html](AppNova_Complete_Architecture.html) - Deep-dive architecture\n"
    "- Swagger UI - `http://127.0.0.1:8002/docs` (live API reference)\n"
)

with open("README.md", encoding="utf-8") as f:
    content = f.read()

# Inject SVG block after the first --- separator
if "AppNova_Frontend_Architecture.svg" not in content:
    content = content.replace("\n---\n", "\n---\n" + SVG_BLOCK, 1)

# Append Related docs footer if missing
if "## Related docs" not in content:
    content = content.rstrip("\n") + "\n" + RELATED_DOCS_BLOCK

# Fix agent count — AppNovaAI README may say 14 (includes removed discovery agent)
# Actual AGENT_REGISTRY has 13 entries; discovery is not registered.
import re
content = re.sub(r"\*\*14 specialist agents\*\*", "**13 specialist agents**", content)
content = re.sub(r"## 🤖 The 14 specialist agents", "## 🤖 The 13 specialist agents", content)
# Remove the discovery row from the agents table if present
content = re.sub(r"\| `discovery` \|[^\n]+\n", "", content)

with open("README.md", "w", encoding="utf-8") as f:
    f.write(content)

print("README.md patched.")
