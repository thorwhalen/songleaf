# Vendored front-end code

`songleaf/data/web/vendor/` holds code the page loads that songleaf did not write. It ships in the wheel and is served by `songleaf.web` at `/ui/vendor/...`, so the page needs no build step and no CDN at run time.

| File | What | From | Licence |
|---|---|---|---|
| `zodal-groups.js` | `defineGroups`, `toSnapshot` (`@zodal/groups-core`); `renderTree`, `renderTagInput`, `renderTagMenu`, `renderGroupChips` (`@zodal/groups-ui-vanilla`), bundled with `zod` as one ES module | [i2mint/zodal-groups](https://github.com/i2mint/zodal-groups) at commit `094a74e` (the touch pass, i2mint/zodal-groups#22; not yet on npm) | MIT; zod MIT |
| `zodal-groups.css` | the vanilla renderers' styles (`currentColor` based, so they follow the page's paper) | the same commit | MIT |

Rebuild with `misc/vendor/build_zodal_groups.sh [REF]`. When zodal-groups 0.2.0 or later is on npm, switch the script to the npm packages and record the version here.
