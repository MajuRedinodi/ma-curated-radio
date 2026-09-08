# Working on this

## Shipping a version

1. Bump `"version"` in `custom_components/ma_curated_radio/manifest.json`
2. Push a matching `vX.Y.Z` tag
3. Publish a **GitHub Release** from that tag

HACS reads Releases, not tags. A bare tag is invisible to it. HACS also
only re-checks downloaded repositories every 48 hours, so use the repo's
⋮ → **Update information** rather than waiting.

## Before pushing

`strings.json` and `translations/en.json` must be byte-identical, JSON and
YAML must parse, and `ruff check` and `pytest` must pass.

## Keep the README dashboard in step

The **A dashboard to paste in** section of the README is the dashboard
actually in use, not an illustration. It is the first thing a new user
gets, and a dashboard that references an entity the integration no longer
creates renders as an error card rather than as nothing.

So any change to the entity surface updates it in the same commit:

- a new or removed `switch`, `select`, `number`, `sensor` or `button`
- a renamed translation key, which renames the entity id
- a new action worth a button
- a changed select option that a `visibility` condition matches on
  (the release dropdowns match `Nothing to release` by exact string)

Entity ids in that YAML use the `family_room_stereo` slug, which readers
are told to find and replace with their own. Keep that slug consistent
throughout rather than genericising it: one placeholder that is obviously
a real example beats a mix of styles.

### What deliberately stays out

The dashboard on the maintainer's own instance also carries a search box
that starts a station: an `input_text`, an `input_select` of results, and
two scripts driving `music_assistant.search`. None of that is in the
README, and it must not be, because none of it is created by the
integration. A card referencing a helper the reader does not have is the
error card this rule exists to prevent.

The right fix is to move that feature into the integration as a `text`
entity plus a couple of buttons. Until then the divergence is deliberate,
and this note is here so the next person does not helpfully "fix" it.
