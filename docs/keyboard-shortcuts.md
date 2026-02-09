# Haven-TUI Keyboard Shortcuts Reference

Complete reference of all keyboard shortcuts for Haven TUI.

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│ Haven-TUI Keyboard Shortcuts                                │
├─────────────────────────────────────────────────────────────┤
│ Navigation                                                   │
│   ↑/↓ or j/k    Move up/down in list                        │
│   Enter         View video details                          │
│   b or Esc      Back to previous view                       │
│   q             Quit application                            │
│                                                              │
│ Display                                                      │
│   r             Refresh data                                │
│   a             Toggle auto-refresh                         │
│   g             Toggle speed graph pane                     │
│   ?             Show help                                   │
│                                                              │
│ Filters & Search                                             │
│   f             Open filter dialog                          │
│   /             Search videos                               │
│   s             Sort options                                │
│                                                              │
│ Batch Operations                                             │
│   Space         Select/unselect video                       │
│   Ctrl+a        Select all visible                          │
│   Ctrl+r        Retry selected failed videos                │
│   Delete        Remove selected from queue                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Global Shortcuts

These shortcuts work from any view in the TUI.

| Shortcut | Action | Description |
|----------|--------|-------------|
| `q` | Quit | Exit the application |
| `Q` | Force Quit | Exit immediately without confirmation |
| `?` | Help | Show context-sensitive help |
| `F1` | Help | Show help (alternative) |

---

## Navigation Shortcuts

### List Navigation

| Shortcut | Action |
|----------|--------|
| `↑` | Move up one item |
| `↓` | Move down one item |
| `j` | Move down (vim-style) |
| `k` | Move up (vim-style) |
| `Home` | Jump to first item |
| `End` | Jump to last item |
| `Page Up` | Scroll up one page |
| `Page Down` | Scroll down one page |
| `Ctrl+Home` | Jump to top |
| `Ctrl+End` | Jump to bottom |

### View Navigation

| Shortcut | Action | Context |
|----------|--------|---------|
| `Enter` / `Return` | Select / Open | Main list |
| `Enter` | Confirm | Dialogs |
| `b` | Back | Any view |
| `Esc` | Back / Cancel | Any view |
| `d` | Details | Main list |
| `Tab` | Next widget | Forms |
| `Shift+Tab` | Previous widget | Forms |

---

## Main View Shortcuts

### Data Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `r` | Refresh | Manually refresh video list |
| `a` | Auto-refresh | Toggle auto-refresh on/off |
| `R` | Force Refresh | Refresh ignoring cache |

### Display Toggles

| Shortcut | Action | Description |
|----------|--------|-------------|
| `g` | Toggle Graph | Show/hide speed graph pane |
| `G` | Graph Options | Configure graph display |
| `z` | Zebra Stripes | Toggle alternating row colors |
| `Z` | Compact Mode | Toggle compact display |

### View Switching

| Shortcut | Action | Description |
|----------|--------|-------------|
| `A` | Analytics | Open analytics dashboard |
| `L` | Event Log | View system event log |
| `V` | Video Log | View logs for selected video |
| `1` | Main View | Return to main pipeline view |
| `2` | Analytics | Switch to analytics view |
| `3` | Events | Switch to event log view |

---

## Filter and Search Shortcuts

### Quick Filters

| Shortcut | Action | Description |
|----------|--------|-------------|
| `c` | Toggle Completed | Show/hide completed videos |
| `f` | Toggle Failed | Show/hide failed videos |
| `e` | Errors Only | Show only videos with errors |
| `x` | Clear Filters | Remove all active filters |
| `X` | Reset View | Clear filters and reset sort |

### Search

| Shortcut | Action | Description |
|----------|--------|-------------|
| `/` | Search | Open search prompt |
| `Ctrl+f` | Search | Alternative search key |
| `n` | Next Result | Find next search match |
| `N` | Previous Result | Find previous search match |
| `Esc` | Clear Search | Exit search mode |

### Advanced Filters

| Shortcut | Action | Description |
|----------|--------|-------------|
| `F` | Filter Dialog | Open detailed filter dialog |
| `p` | Filter by Plugin | Cycle through plugin filters |
| `s` | Filter by Stage | Cycle through stage filters |
| `t` | Filter by Status | Cycle through status filters |

---

## Sorting Shortcuts

### Sort Control

| Shortcut | Action | Description |
|----------|--------|-------------|
| `s` | Cycle Sort Field | Change sort field (date → title → progress → speed → size → stage) |
| `S` | Toggle Order | Switch ascending/descending |
| `Ctrl+s` | Sort Dialog | Open sort options dialog |

### Direct Sort Selection

Hold `Alt` and press the first letter of the field:

| Shortcut | Sort By | Description |
|----------|---------|-------------|
| `Alt+d` | Date Added | When video entered pipeline |
| `Alt+t` | Title | Alphabetical by title |
| `Alt+p` | Progress | By completion percentage |
| `Alt+s` | Speed | By current transfer speed |
| `Alt+z` | Size | By file size |
| `Alt+g` | Stage | By pipeline stage |

---

## Batch Mode Shortcuts

### Enter/Exit Batch Mode

| Shortcut | Action | Description |
|----------|--------|-------------|
| `b` | Toggle Batch Mode | Enter or exit batch mode |
| `B` | Batch Menu | Open batch operations menu |
| `Esc` | Exit Batch Mode | Exit without clearing selection |

### Selection Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Space` | Toggle Selection | Select/deselect current video |
| `Ctrl+a` | Select All | Select all visible videos |
| `Ctrl+Shift+a` | Select All (All) | Select all videos (ignore filters) |
| `c` | Clear Selection | Deselect all videos |
| `Ctrl+i` | Invert Selection | Toggle all selections |
| `Shift+↑/↓` | Range Select | Select range of videos |

### Batch Actions

| Shortcut | Action | Description |
|----------|--------|-------------|
| `r` / `Ctrl+r` | Retry | Retry failed selected videos |
| `x` / `Delete` | Remove | Remove selected from queue |
| `Ctrl+x` | Force Remove | Remove without confirmation |
| `e` | Export | Export selected to JSON |
| `Ctrl+e` | Export CSV | Export selected to CSV |
| `Ctrl+c` | Copy | Copy selected IDs to clipboard |
| `p` | Pause | Pause selected active videos |
| `Ctrl+p` | Resume | Resume selected paused videos |

### Batch Mode Indicators

When in batch mode, the footer shows:
```
Batch: 5 selected | [a] All  [c] Clear  [r] Retry  [x] Remove  [e] Export  [Esc] Exit
```

---

## Detail View Shortcuts

### Navigation

| Shortcut | Action | Description |
|----------|--------|-------------|
| `b` / `Esc` | Back | Return to main list |
| `↑/↓` | Scroll | Scroll through details |
| `Tab` | Next Section | Jump to next info section |
| `Shift+Tab` | Previous Section | Jump to previous section |

### Actions

| Shortcut | Action | Description |
|----------|--------|-------------|
| `r` | Retry | Retry failed stages |
| `R` | Force Retry | Retry all stages |
| `l` | Logs | View event logs |
| `L` | Full Logs | View complete log history |
| `g` | Toggle Graph | Show/hide speed graph |
| `G` | Graph Stage | Cycle through stage graphs |
| `p` | Pause | Pause this video's processing |
| `P` | Resume | Resume this video's processing |
| `d` | Download Info | Show download details |
| `i` | Video Info | Show video metadata |

### Detail View Sections

| Shortcut | Action | Description |
|----------|--------|-------------|
| `1` | Info Section | Jump to video info |
| `2` | Pipeline Section | Jump to pipeline progress |
| `3` | Results Section | Jump to results |
| `4` | Graph Section | Jump to speed graph |

---

## Analytics Dashboard Shortcuts

### Navigation

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Esc` / `b` / `q` | Back | Return to main view |
| `↑/↓` | Scroll | Scroll through dashboard |
| `Tab` | Next Chart | Focus next chart |
| `Shift+Tab` | Previous Chart | Focus previous chart |

### Data Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `r` | Refresh | Refresh analytics data |
| `a` | Auto-refresh | Toggle auto-refresh |
| `1` | 7 Days | Show last 7 days |
| `2` | 30 Days | Show last 30 days |
| `3` | 90 Days | Show last 90 days |

### Chart Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `d` | Daily View | Show daily breakdown |
| `w` | Weekly View | Show weekly breakdown |
| `m` | Monthly View | Show monthly breakdown |
| `s` | Stage Toggle | Show/hide stage breakdown |
| `p` | Plugin Toggle | Show/hide plugin breakdown |

---

## Event Log View Shortcuts

### Navigation

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Esc` / `b` | Back | Return to previous view |
| `↑/↓` | Scroll | Scroll through events |
| `Page Up` | Page Up | Scroll up one page |
| `Page Down` | Page Down | Scroll down one page |
| `Home` | Beginning | Jump to first event |
| `End` | End | Jump to last event |
| `Ctrl+f` | Find | Search in logs |
| `n` | Next Match | Find next occurrence |
| `N` | Previous Match | Find previous occurrence |

### Filtering

| Shortcut | Action | Description |
|----------|--------|-------------|
| `f` | Filter | Open filter dialog |
| `e` | Errors Only | Show only errors |
| `w` | Warnings+ | Show warnings and errors |
| `i` | Info+ | Show info and above |
| `d` | Debug | Show all levels |
| `v` | Video Filter | Filter by selected video |
| `c` | Clear Filter | Remove all filters |

### Log Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `r` | Refresh | Refresh logs |
| `a` | Auto-scroll | Toggle auto-scroll |
| `t` | Tail | Follow new events |
| `s` | Save | Save logs to file |
| `Ctrl+c` | Copy | Copy selected lines |

---

## Filter Dialog Shortcuts

When the filter dialog is open:

| Shortcut | Action |
|----------|--------|
| `↑/↓` | Navigate between filter options |
| `←/→` | Toggle options / Navigate tabs |
| `Space` | Toggle checkbox |
| `Enter` | Apply filters |
| `Esc` | Cancel and close |
| `Tab` | Next field |
| `Shift+Tab` | Previous field |
| `Ctrl+r` | Reset to defaults |

---

## Configuration Shortcuts

### In-App Configuration

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Ctrl+o` | Options | Open options dialog |
| `Ctrl+,` | Settings | Open settings view |
| `Ctrl+r` | Refresh Rate | Change refresh interval |
| `Ctrl+g` | Graph Settings | Configure speed graphs |
| `Ctrl+f` | Filter Settings | Configure default filters |

### Display Settings

| Shortcut | Action | Description |
|----------|--------|-------------|
| `+` / `=` | Increase | Increase refresh rate |
| `-` | Decrease | Decrease refresh rate |
| `Ctrl++` | Zoom In | Increase text size |
| `Ctrl+-` | Zoom Out | Decrease text size |
| `Ctrl+0` | Reset Zoom | Reset text size |
| `F11` | Fullscreen | Toggle fullscreen |

---

## Emergency Shortcuts

| Shortcut | Action | When to Use |
|----------|--------|-------------|
| `Ctrl+c` | Interrupt | Stop current operation |
| `Ctrl+\` | Force Quit | Emergency exit |
| `Ctrl+l` | Redraw | Fix display corruption |
| `F5` | Refresh | Force screen redraw |

---

## Shortcut Combinations

### Power User Combos

| Combo | Result |
|-------|--------|
| `b` → `a` → `r` | Enter batch mode, select all, retry |
| `e` → `c` → `x` | Show errors, clear selection, clear filters |
| `/` + query + `Enter` → `s` | Search, then sort results |
| `A` → `r` → `Esc` | View analytics, refresh, return |
| `g` → `↑/↓` → `Enter` | Show graph, select video, view details |

### Quick Workflows

**Retry All Failed:**
```
e (errors only) → b (batch mode) → a (select all) → r (retry)
```

**Export Completed:**
```
c (show completed) → b (batch mode) → a (select all) → e (export)
```

**Check Recent Errors:**
```
L (event log) → e (errors only) → ↑/↓ (review)
```

---

## Platform-Specific Notes

### macOS

- Use `Cmd` instead of `Ctrl` where noted
- `Cmd+q` will quit the application
- `Cmd+plus/minus` for zoom

### Windows

- `Alt+F4` closes the application
- `Ctrl+Plus` (numpad) for zoom
- Some terminals may require `Fn` for function keys

### Linux

- Standard shortcuts apply
- Some terminals may intercept certain combinations
- Use `Ctrl+Shift+c/v` for copy/paste in terminal

---

## Accessibility Shortcuts

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Alt+h` | High Contrast | Toggle high contrast mode |
| `Alt+z` | Large Text | Increase text size |
| `Alt+s` | Screen Reader | Toggle screen reader hints |
| `Alt+m` | Monochrome | Disable colors |
| `Tab` | Focus | Move between interactive elements |

---

## Custom Shortcuts

You can customize shortcuts in the configuration file:

```toml
[tui.shortcuts]
refresh = "r"
quit = "q"
help = "?"
batch_mode = "b"
toggle_graph = "g"
# ... etc
```

See [Configuration](configuration.md) for details.

---

## Tips

1. **Learn vim navigation** (`j/k`) for faster movement
2. **Use batch mode** (`b`) for managing multiple videos
3. **Press `?`** anytime for context-sensitive help
4. **`Esc` always takes you back** - muscle memory!
5. **Filters persist** until you clear them (`x`)
