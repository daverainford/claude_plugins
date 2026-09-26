# claude_plugins

My personal Claude Code plugin marketplace.

## Install

Add the marketplace once, then install any plugin from it:

```
/plugin marketplace add daverainford/claude_plugins
/plugin install <plugin-name>@david-plugins
```

Or as one line from your shell:

```
claude plugin marketplace add daverainford/claude_plugins && claude plugin install bioinformatics-workflow@david-plugins
```

Plugin dependencies install automatically.

## Plugins

| Plugin | What it does |
| --- | --- |
| [`bioinformatics-workflow`](bioinformatics-workflow/) | Staged, human-reviewed cancer genomics analysis on AWS Batch, with literature-grounded interpretation. |

Each plugin has its own README with setup and usage.

## Try a plugin locally

Skip the marketplace and load a plugin straight from its folder:

```
claude --plugin-dir ./<plugin-name>
```

## Add a new plugin

1. Create a folder at the top level: `<plugin-name>/`
2. Add `<plugin-name>/.claude-plugin/plugin.json` with a name, version, and description.
3. Add whatever the plugin needs: `skills/`, `agents/`, `hooks/`, `output-styles/`, `.mcp.json`.
4. Register it in `.claude-plugin/marketplace.json`.
5. Add a row to the table above.
