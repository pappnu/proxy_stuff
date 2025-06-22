# Proxy stuff

A plugin for additional [Proxyshop](https://github.com/Investigamer/Proxyshop) templates.

## Templates

- Borderless Showcase
- Borderless Enhanced
- Vectorized Borderless Planeswalker

## Requirements

- A version of [Proxyshop](https://github.com/Investigamer/Proxyshop) that matches it's main-branch and has all of my pull requests merged to it (not all of them are vital, but this is the setup I test my plugin with). There's an [unofficial build](https://github.com/alex-taxiera/Proxyshop/releases) available that should fulfill this criteria.
- Photoshop 23.5 or newer

## Installation

1. Download the latest [release](https://github.com/pappnu/proxy_stuff/releases) and extract the archive to your plugins folder (`/path/to/your/Proxyshop/plugins/`). You should end up with the following file structure:
   ```
   Proxyshop
   ├── plugins
   │   └── proxy_stuff
   │       ├── manifest.yml
   │       └── ...
   ├── Proxyshop.exe
   └── ...
   ```
2. Download the templates via Proxyshop's updater or manually from [here](https://drive.google.com/drive/folders/1Q4JgzLOWCocjh56MKTfHgSPGMS-QQtOL).

## Troubleshooting

### The plugin won't load

Ensure that you have the latest Proxyshop build (see [Requirements](#requirements)) and that your installation follows the aforementioned file structure (see [Installation](#installation)).

### Confirmation dialog halts the rendering

If you get a confirmation dialog that says "This opeartion will turn a live shape into a regular path. Continue?", tick the "Don't show again" checkbox and press "Yes". Then try rendering the card again.

### File not found error is raised

If you get an error similar to `FileNotFoundError: [Errno 2] No such file or directory: 'path\to\proxy_stuff\dist\<some_name>.js'`, you should use a [prebuilt release](https://github.com/pappnu/proxy_stuff/releases) or transpile the TypeScript scripts yourself as described in the [Development environment](#development-environment) section.

### None of the above help

You could open an issue. Make sure to attach the error log, if one exists, from Proxyshop to your issue.

## Development environment

Node.js is required in addition to the basic requirements.

Install dependencies

```
npm install
```

Transpile scripts

```
npm run build
```

## Credits

Thanks to all to those that have helped in various ways with the development of this plugin:

- Kapa the Bard, creator of Polymath Proxy
- [Alex Taxiera](https://github.com/alex-taxiera)

This plugin uses assets from existing Proxyshop templates, so look at [Proxyshop's credits](https://github.com/Investigamer/Proxyshop#-credits) too see whose work those are.

## Licence

MIT
