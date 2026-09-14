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

## Two test suites

`tests/` holds the rules: they import the pure modules directly, need
nothing but pytest, and run in under a second. Anything that can be a
pure function belongs there, and several have been moved out of the
wiring on purpose so they could be.

`tests/integration/` runs against a real Home Assistant and needs
`pip install -r requirements_test.txt`. Without it those tests skip
rather than fail, so the fast suite still works on a machine with nothing
set up. They cover what the fast suite cannot reach: setting up, unloading
and removing an entry, the options flow, and following a renamed player.
Every bug in that layer so far was found by reading rather than by
testing, which is what these exist to change.

The framework pins the Home Assistant version it was built against, so
the integration suite proves the wiring against a slightly older Home
Assistant than the one you are probably running.

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
scripts to drive them. The integration provides the hard half of that as
the `ma_curated_radio.search` action, but the helpers and scripts are not
created by the integration, so the cards that use them stay out of the
README. A card referencing a helper the reader does not have is the error
card this rule exists to prevent.

Moving the rest in, as a `text` entity plus a button, would close the gap.
Until then the divergence is deliberate, and this note is here so the next
person does not helpfully "fix" it.
