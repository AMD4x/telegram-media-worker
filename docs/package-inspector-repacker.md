# Package Inspector / Repacker

Package Inspector / Repacker is a two-step package workflow family for sources that need browsing before final Telegram delivery.

It is designed for bot-side flows where the bot first asks GitHub to inspect a source, then shows a Package Browser UI so the admin can select, rename, and repack only the needed items.

## Workflow pair

| Workflow | Purpose | Main output |
|---|---|---|
| `package-inspect.yml` | Inspect a package-like source and build an item manifest. | Encrypted `.enc` manifest for the bot; optional Telegram report. |
| `package-repack.yml` | Rebuild selected manifest items into a new ZIP. | Telegram ZIP document, with split ZIP parts when needed. |

## Supported source categories

`package-inspect.yml` can be used for package-like sources such as:

- archives supported by the worker tools,
- direct files,
- magnet links,
- direct `.torrent` files,
- directory listings,
- URL lists.

Actual success depends on source availability, archive support in the worker image, torrent metadata availability, and network access from the GitHub runner.

## Bot-side flow

1. The bot receives a source URL and confirms that the admin requested package inspection.
2. The bot triggers `package-inspect.yml` with `source_url`, progress IDs, and a unique `dispatch_key`.
3. The workflow builds `manifest.json`, encrypts it, and stores it as `.package_manifests/<dispatch_key>.enc`.
4. The bot reads and decrypts the `.enc` manifest with `PACKAGE_MANIFEST_KEY`.
5. The bot deletes the `.enc` file after successful read/decrypt.
6. The bot shows Package Browser with folders, files, selected items, output ZIP name, and rename actions.
7. The bot triggers `package-repack.yml` with selected indexes and optional `rename_map_json`.
8. The workflow sends the final ZIP to Telegram.

## Package Browser ordering and rename behavior

Package Inspector / Repacker uses the manifest indexes as stable workflow data, while the Telegram bot owns the interactive Package Browser. The newest rename should stay visible in long Package Browser lists so the admin can verify the change immediately before running the final repack.

Recommended bot behavior:

- keep a bot-side `rename_priority` list,
- store original manifest paths, not current display paths,
- when a selected file is renamed, move its original path to the newest position,
- sort newest renamed files first,
- keep other renamed files before unchanged files,
- remove the path from priority when the rename is reset.

This state is not sent to GitHub. `package-repack.yml` only receives the final selected indexes and `rename_map_json`.

## Repack inputs

| Input | Required | Default | Notes |
|:---:|:---:|:---:|---|
| `source_url` | yes | - | Same original URL used by Package Inspector. |
| `keep_indexes` | no | empty | Preferred include list such as `1,2,5-7`. |
| `delete_indexes` | no | empty | Exclusion list used only when `keep_indexes` is empty. |
| `rename_map_json` | no | empty | JSON object mapping original manifest paths to new internal ZIP paths. |
| `output_filename` | no | `package_output.zip` | Final ZIP name. |
| `split_part_mib` | no | `1900` | Split size in MiB for oversized ZIP output. |

## Privacy notes

- `PACKAGE_MANIFEST_KEY` must stay private.
- `.package_manifests/*.enc` files are temporary bot handoff files.
- `.package_manifests/*.json` and `.package_manifests/*.enc` should stay ignored by Git.
- The bot should not print manifest file names, source URLs, selected indexes, or rename maps into public logs.
- The bot should delete the encrypted manifest after successful read/decrypt.

## Relationship to torrent workflow

`torrent-document-local-api.yml` is for direct torrent document delivery.

Package Inspector / Repacker is different: it lets the bot inspect a package-like source, choose only some items, optionally rename internal paths, and output a new ZIP.
