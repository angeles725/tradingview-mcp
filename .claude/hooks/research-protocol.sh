#!/usr/bin/env bash
# SessionStart hook - Research-SDD protocol for tradingview-mcp.
# Mirror of the niagara-research hook, parameterized. Copy it to:
#   <TARGET>/.claude/hooks/research-protocol.sh
# and register it in <TARGET>/.claude/settings.json (matcher startup|resume|clear).
# Adapted for the nested corpus in this source repository.
set -euo pipefail

read -r -d '' CTX <<'EOF' || true
RESEARCH PROTOCOL - tradingview-mcp (Research-SDD)

When conducting Research-SDD work in this project, treat the TradingView MCP
implementation as the READ-ONLY subject. Follow this order:

1. FIRST search the project's own .md blocks (truth already distilled):
   - corpus/tradingview-block*.md
   - corpus/INDEX.md
   - corpus/CATALOG.md
   Review them before opening any tool.

2. Toolbelt tools (Research-SDD) — pick based on the artifact type:
   - profile-target.sh   -> classifies binaries and suggests the wrapper
   - decompile-java.sh   -> .jar/.class (Vineflower/CFR/Procyon, javap)
   - decompile-net.sh    -> .dll/.exe .NET (ilspycmd)
   - decompile-native.sh -> native ELF/PE (Ghidra headless / r2)  | ghidra-mcp for directed analysis
   - scan-firmware.sh    -> firmware/packaged (binwalk + yara)
   - fetch-doc.sh        -> download and PRESERVE datasheets/manuals/forums in sources/
   (Kit: /home/cristian/investigacion/sdd-investigacion/research-sdd/toolbelt/)

3. PRIMARY SOURCES of the subject:
   - src/ and tests/
   - README.md and SECURITY.md
   - corpus/sources/probes/ for preserved offline receipts

4. PROVENANCE AND CERTAINTY (mandatory markers on every claim):
   [CERT] local primary · [CERT-doc] official document (sources/) · [CERT-web] official web ·
   [CERT-a] forum/secondary · [INFER] deduction. No citation ⇒ [INFER] or omit.

5. EXTERNAL EVIDENCE: if you find a relevant datasheet/manual/forum/link, DOWNLOAD it with
   fetch-doc.sh (lands in sources/ + registered in SOURCES.md) and cite the local file.

ACTION AT START: review corpus/INDEX.md and the relevant blocks before opening
source files or choosing a toolbelt tool.
EOF

jq -n --arg ctx "$CTX" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
