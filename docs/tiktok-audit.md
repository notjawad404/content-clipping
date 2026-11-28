# TikTok Content Posting API audit

Until the app passes TikTok's audit, every Direct Post is forced to `SELF_ONLY`, and the TikTok account has to be
private while posting. Passing the audit removes both limits.

## 1. Publish the website (privacy policy and terms)

The pages live in `site/` and are deployed by `.github/workflows/pages.yml`.

1. Commit and push to `master`.
2. Turn on Pages with GitHub Actions as the source (do this once):
   `gh api -X POST repos/notjawad404/content-clipping/pages -f build_type=workflow`
   (or Settings → Pages → Source: GitHub Actions).
3. Check the pages load:
   - https://notjawad404.github.io/content-clipping/
   - https://notjawad404.github.io/content-clipping/privacy.html
   - https://notjawad404.github.io/content-clipping/terms.html

## 2. Fill in the app in the developer portal

developers.tiktok.com → Manage apps → your app.

| Field | Value |
|---|---|
| App icon | 1024×1024 PNG, no TikTok logo |
| App name | Clip Studio (must not contain "TikTok") |
| Category | Video / Content creation |
| Description | Desktop tool that cuts long videos into short clips and lets creators review and post them to their own TikTok account. |
| Terms of Service URL | https://notjawad404.github.io/content-clipping/terms.html |
| Privacy Policy URL | https://notjawad404.github.io/content-clipping/privacy.html |
| Platform | Desktop (and Web with the site above as the website URL, if the form asks for one) |

If the portal asks you to verify the URL prefix, download the signature `.txt` file it gives you, put it in
`site/`, push, and press Verify.

### Products and scopes

- **Login Kit**: redirect URI `http://localhost:8723/callback/`
- **Content Posting API**: turn on **Direct Post**
- Scopes: `user.info.basic`, `video.upload`, `video.publish`

When the form asks how each scope is used:

- `user.info.basic`: shows the connected account's avatar, nickname and username on the posting screen so the creator
  knows which account they are posting to.
- `video.upload` / `video.publish`: uploads the clip the creator picked and publishes it with the title, privacy
  level, interaction settings and content disclosure they chose on the posting screen. Nothing is posted until they
  press Post.

## 3. Demo video

TikTok wants one recording of the whole flow, from connecting the account to the finished post. MP4 or MOV, under
50 MB each, up to 5 files.

The recording should show:

1. The website and its privacy policy and terms pages.
2. Opening Clip Studio (`uv run python scripts/clip_studio.py`) and pressing **Connect TikTok**, including TikTok's
   login and permission screen.
3. Picking a clip and opening **Post to TikTok**: the account's name and avatar, the clip preview, the editable title,
   the privacy dropdown with nothing selected by default, the Comment/Duet/Stitch checkboxes off by default, and the
   content disclosure toggle (Your brand → "Promotional content", Branded content → "Paid partnership", and "Only me"
   turning off for branded content).
4. Pressing Post, the processing message, and the finished status.
5. The video showing up on the TikTok profile (in the app or on tiktok.com).

The account must be private while you record, because the app is still unaudited, so pick **Only me**. Parts 1, 3
and 4 can be recorded automatically with `output/tiktok_audit_demo/record.py` while Clip Studio is running. Record
parts 2 and 5 yourself with Win+Alt+R (Xbox Game Bar), or record the whole flow that way in one take.

## 4. Submit

1. Upload the demo video, check every field, and press **Submit for review**. App review usually takes a few days.
2. Once the app is approved, open the Content Posting API product page and send the **Direct Post audit** form. It
   asks how the app works, how many creators and posts a day you expect (say 1 creator, about 3 posts a day), and
   for the same demo video.
3. Reply to any follow-up emails from TikTok. Rejections nearly always name the guideline that was missed.

## 5. After approval

- Make the TikTok account public again.
- Post public clips from Clip Studio with **Everyone** selected.
- TikTok's sharing guidelines require the creator to review and confirm each post. Posting public videos from the
  unattended cron (`tiktok_privacy: PUBLIC_TO_EVERYONE` in `config/publish.yaml`) breaks that rule and can get the
  app's access revoked. Keep the cron on `SELF_ONLY` or `manual` mode, and post public videos through Clip Studio.
