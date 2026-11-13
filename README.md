# NovelAI V4.5 Bridge — Nodnaba

This PUBLIC repository connects a user-initiated GitHub request to **one NovelAI V4.5 image generation**. A ChatGPT GitHub integration can create a scene issue, and GitHub Actions checks the author before performing a single API call.

## Status
- Python V4.5 client: installed.
- Owner-only GitHub Actions workflow: installed.
- Unit/security tests: installed.
- Dry-run in GitHub Actions: to verify.
- NovelAI Persistent API Token: NOT connected.
- Live image generation: NOT tested.

## Security rules
- Never paste the NovelAI API token in chat, issues, README, or code.
- GitHub Secrets can protect the token from casual readers, but do not guarantee zero risk.
- PUBLIC issues, scene prompts, logs, and Actions artifacts may be seen by other people. Do not submit confidential content.
- Do not add collaborators or enable untrusted workflows without reviewing their access to Secrets.
- The code fixes the API host and model, blocks arbitrary field injection, restricts owner access, sets a single image, and has no automatic retries or schedules.
- NovelAI requires generation requests to be human-initiated. One user request equals at most one live generation.
- Original character reference images are NOT included in this public repository. References named nari/kangchan cannot work until secure storage is separately arranged or you expressly approve publishing them.
- GitHub Actions runner cost and NovelAI subscription/Anlas are different billing matters.

## First: no-cost dry-run
Open https://github.com/wizz-338/Novel-ai/actions and select the NovelAI V4.5 workflow, then Run workflow. Enter the following one-line scene JSON:

    {"prompt":"1girl, short black bob, freckles, calm neutral expression, matte anime cel shading, rainy bus stop","dry_run":true}

An alternative is an owner-authored GitHub issue whose title starts with [NAI] and whose body is the same JSON. An unauthenticated person's issue will skip the job. The resulting dry-run.json appears as an Actions artifact (3-day retention) and does not call NovelAI.

## Next: configure account token
1. NovelAI → Settings → Account → Get Persistent API Token.
2. This repository → Settings → Secrets and variables → Actions → New repository secret.
3. Name exactly: NOVELAI_API_TOKEN. Store token there ONLY; do not send it here.
4. In Settings → Actions → General, keep default workflow permissions read-only. Protect main from unreviewed changes where possible.

NovelAI documentation warns its persistent token is sensitive account material, including access related to story encryption. Rotating the token invalidates previous tokens.

## After explicit approval for a single live image
Submit a NEW owner issue with title [NAI] scene title and JSON body (example):

    {
      "prompt":"1girl, short black bob, freckles, neutral face, matte cel shading, realistic anatomy, rainy bus stop",
      "negative_prompt":"shiny skin, cartoon grin",
      "width":1024,
      "height":1024,
      "steps":24,
      "scale":5,
      "seed":0,
      "reference":null,
      "dry_run":false
    }

On success, retrieve the output in GitHub → Actions → the run → Artifacts. Check face, body and hands before any fal video task.

## Development
Test locally with: python3 -m unittest discover -s tests -v

The API URL is fixed to https://image.novelai.net/ai/generate-image and the model to nai-diffusion-4-5-full. No additional Python packages are needed. Official API docs: https://image.novelai.net/docs/index.html
