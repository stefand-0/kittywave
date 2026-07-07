import curses
import random
import sys

def parse_vcd(filename):
    signals = {}
    events = {}
    depth = 0
    current_time = 0
    events[current_time] = {}
    
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if not parts: continue
            if parts[0] == '\$scope': depth += 1
            elif parts[0] == '\$upscope': depth = max(0, depth - 1)
            elif parts[0] == '\$var':
                if len(parts) >= 5: signals[parts[3]] = {'name': parts[4], 'depth': depth}
            elif parts[0].startswith('#'):
                current_time = int(parts[0][1:])
                if current_time not in events: events[current_time] = {}
            else:
                first = parts[0]
                if first and (first[0] in ('0', '1', 'x', 'z') or first[0] == 'b'):
                    val = first if first[0] == 'b' else first[0]
                    sig_id = parts[1] if first[0] == 'b' else first[1:]
                    if sig_id in signals:
                        if current_time not in events: events[current_time] = {}
                        events[current_time][sig_id] = val
    return signals, events, sorted(events.keys())

def get_val_at(sig_id, target_time, events, sorted_times):
    val = '0'
    for t in sorted_times:
        if t <= target_time:
            if sig_id in events[t]: val = events[t][sig_id]
        else: break
    return val

def format_by_radix(val, radix):
    is_bus = val.startswith('b')
    clean_val = val[1:] if is_bus else val
    
    if any(c in clean_val.lower() for c in ('x', 'z')):
        return clean_val.upper()
        
    try:
        num = int(clean_val, 2)
        if radix == 'hex':
            return f"0x{hex(num)[2:].upper()}"
        elif radix == 'dec':
            return str(num)
        else:
            return f"0b{bin(num)[2:]}"
    except:
        return val

def get_next_edge(sig_id, current_time, events, sorted_times, forward=True):
    times = [t for t in sorted_times if sig_id in events[t]]
    if forward:
        future = [t for t in times if t > current_time]
        return future[0] if future else current_time
    else:
        past = [t for t in times if t < current_time]
        return past[-1] if past else current_time

def draw_viewer(stdscr, signals, event_map, timestamps):
    curses.start_color()
    curses.use_default_colors()
    stdscr.keypad(True) 
    color_map = {sig: (i % 7) + 1 for i, sig in enumerate(signals.keys())}
    for i in range(1, 8): curses.init_pair(i, i, -1)

    sig_ids = list(signals.keys())
    selected_sig = 0
    time_offset = 0
    zoom = 1
    radix = 'bin'
    filter_str = ""
    marker_a, marker_b = None, None
    bookmark_time = None
    theme = 'classic'
    show_menu = False
    show_help = False
    help_scroll_offset = 0
    
    help_lines = [
        " SYSTEM:",
        "  h      : Toggle this Help Menu",
        "  q      : Exit App / Close current menu",
        "  z      : Toggle Stored Values Inspector",
        "",
        " NAVIGATION:",
        "  l / r  : Scroll timeline Left / Right",
        "  , / .  : Fast Scroll Left / Right (10x zoom)",
        "  g      : Go To specific Time (nanoseconds)",
        "  u / d  : Select Signal Wire (Up / Down)",
        "  n / p  : Snap to Next / Previous signal edge",
        "",
        " MEASUREMENTS & TOOLS:",
        "  m / k  : Set Marker A / Marker B",
        "  w      : Clear Markers / Reset Delta",
        "  b / v  : Set Bookmark / Jump to Bookmark",
        "  s      : Search forward for a specific signal value",
        "  /      : Filter signals by text string",
        "",
        " VISUALS:",
        "  x      : Toggle Radix display (BIN -> HEX -> DEC)",
        "  t      : Toggle Trace Line Style (Classic -> Block)",
        "",
        " HELP MENU SCROLLING:",
        "  ▲ / ▼  : Scroll up and down this help page!"
    ]
    
    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        
        label_width = 15
        wave_width = w - label_width - 3
        if wave_width < 5: wave_width = 5
        center = wave_width // 2
        cursor_time = time_offset + (center * zoom)
        
        delta = abs(marker_a - marker_b) if (marker_a is not None and marker_b is not None) else 0
        filtered_ids = [s for s in sig_ids if filter_str in signals[s]['name']]
        
        if show_help:
            stdscr.addstr(0, 0, " === KITTYWAVE COMMAND HELP === "[:w-1], curses.A_REVERSE)
            visible_lines = help_lines[help_scroll_offset:]
            for idx, line in enumerate(visible_lines):
                if idx + 2 >= h - 1: break
                stdscr.addstr(idx + 2, 0, line[:w-1])
            stdscr.addstr(h-1, 0, " ▲/▼:Scroll | 'h' or 'q' to return to waves... "[:w-1], curses.A_REVERSE)

        elif show_menu:
            stdscr.addstr(0, 0, " === STORED VALUES INSPECTOR === "[:w-1], curses.A_REVERSE)
            stdscr.addstr(2, 0, f" Display Radix: {radix.upper()} | Theme: {theme.upper()}"[:w-1])
            stdscr.addstr(3, 0, f" Bookmark     : {f'{bookmark_time} ns' if bookmark_time is not None else 'Not Set'}"[:w-1])
            stdscr.addstr(4, 0, f" Marker A / B : {marker_a if marker_a is not None else '-'} / {marker_b if marker_b is not None else '-'} ns"[:w-1])
            stdscr.addstr(5, 0, f" Delta Window : {delta} ns"[:w-1])
            stdscr.addstr(6, 0, f" Cursor Time  : {cursor_time} ns"[:w-1])
            stdscr.addstr(7, 0, " ------------------------------ "[:w-1])
            
            stdscr.addstr(8, 0, f" {'SIGNAL':<15} | VALUE ({radix.upper()})"[:w-1], curses.A_UNDERLINE)
            for idx, sig_id in enumerate(filtered_ids):
                if idx + 10 >= h: break
                raw_val = get_val_at(sig_id, cursor_time, event_map, timestamps)
                formatted_val = format_by_radix(raw_val, radix)
                name = signals[sig_id]['name']
                stdscr.addstr(idx + 10, 0, f" {name[:14]:<15} | {formatted_val}"[:w-1])
                
            stdscr.addstr(h-1, 0, " 'z':Back | 'x':Radix | 'w':Reset Markers | 'h':Help "[:w-1], curses.A_REVERSE)
            
        else:
            status = f" T:{cursor_time}ns | RADIX:{radix.upper()} | Δ:{delta}ns | Bmk:{bookmark_time if bookmark_time is not None else '-'}"
            stdscr.addstr(0, 0, status[:w-1], curses.A_REVERSE)
            
            for i, sig_id in enumerate(filtered_ids):
                if i + 2 >= h - 3: break 
                attr = curses.A_REVERSE if i == selected_sig else curses.A_NORMAL
                color = curses.color_pair(color_map[sig_id])
                
                wave_str = []
                high_char = '█' if theme == 'block' else '¯'
                low_char = ' ' if theme == 'block' else '_'
                
                for x in range(wave_width):
                    t = time_offset + (x * zoom)
                    raw_val = get_val_at(sig_id, t, event_map, timestamps)
                    if x == center: 
                        wave_str.append('|') 
                    else:
                        if raw_val.startswith('b'):
                            wave_str.append('=')
                        else:
                            wave_str.append(high_char if raw_val == '1' else low_char)
                
                indent = "  " * signals[sig_id]['depth']
                label_text = f"{indent}{signals[sig_id]['name'][:10]}"
                stdscr.addstr(i + 2, 0, f"{label_text:<15} | "[:label_width+3], attr)
                stdscr.addstr(i + 2, label_width + 3, "".join(wave_str)[:wave_width], color)
                
            footer1 = " h:Help | q:Exit | z:Menu | x:Radix | w:Clr Δ | t:Theme | g:GoTo"
            footer2 = " u/d:Sig | l/r:Scroll | ,/.:Fast Scroll | m/k:Marker | b/v:Bmk"
            if h > 3:
                stdscr.addstr(h-2, 0, footer1[:w-1], curses.A_REVERSE)
                stdscr.addstr(h-1, 0, footer2[:w-1], curses.A_REVERSE)
                
        stdscr.refresh()
        key = stdscr.getch()
        
        if key == ord('h'):
            show_help = not show_help
            if show_help: 
                show_menu = False
                help_scroll_offset = 0
        elif key == ord('z'):
            show_menu = not show_menu
            if show_menu: show_help = False
        elif key == curses.KEY_UP and show_help:
            help_scroll_offset = max(0, help_scroll_offset - 1)
        elif key == curses.KEY_DOWN and show_help:
            max_offset = max(0, len(help_lines) - (h - 3))
            help_scroll_offset = min(max_offset, help_scroll_offset + 1)
        elif key == ord('x'):
            if radix == 'bin': radix = 'hex'
            elif radix == 'hex': radix = 'dec'
            else: radix = 'bin'
        elif key == ord('w'):
            marker_a, marker_b = None, None
        elif key == ord('t'):
            theme = 'block' if theme == 'classic' else 'classic'
        elif key == ord('b'):
            bookmark_time = cursor_time
        elif key == ord('v'):
            if bookmark_time is not None:
                time_offset = max(0, bookmark_time - (center * zoom))
        elif key == ord('q'): 
            if show_help: show_help = False
            elif show_menu: show_menu = False
            else: break
        elif not show_menu and not show_help:
            if key == ord('u') or key == curses.KEY_UP: selected_sig = max(0, selected_sig - 1)
            elif key == ord('d') or key == curses.KEY_DOWN: selected_sig = min(len(filtered_ids) - 1, selected_sig + 1)
            elif key == ord('i'): zoom = max(1, zoom - 1)
            elif key == ord('o'): zoom += 1
            elif key == ord('l') or key == curses.KEY_LEFT: time_offset = max(0, time_offset - zoom)
            elif key == ord('r') or key == curses.KEY_RIGHT: time_offset += zoom
            elif key == ord(','): time_offset = max(0, time_offset - (10 * zoom))
            elif key == ord('.'): time_offset += (10 * zoom)
            elif key == ord('m'): marker_a = cursor_time
            elif key == ord('k'): marker_b = cursor_time
            elif key == ord('n') and filtered_ids: 
                time_offset = get_next_edge(filtered_ids[selected_sig], cursor_time, event_map, timestamps, True) - (center * zoom)
            elif key == ord('p') and filtered_ids: 
                time_offset = get_next_edge(filtered_ids[selected_sig], cursor_time, event_map, timestamps, False) - (center * zoom)
            elif key == ord('g'):
                if h > 3: stdscr.addstr(h-3, 0, "Jump to Time (ns): ")
                curses.echo()
                try:
                    target_t = int(stdscr.getstr().decode('utf-8').strip())
                    time_offset = max(0, target_t - (center * zoom))
                except: pass
                curses.noecho()
            elif key == ord('s') and filtered_ids:
                if h > 3: stdscr.addstr(h-3, 0, "Search Value for Current Signal: ")
                curses.echo()
                search_val = stdscr.getstr().decode('utf-8').strip().upper()
                curses.noecho()
                target_sig = filtered_ids[selected_sig]
                found_time = None
                for t in timestamps:
                    if t > cursor_time:
                        raw_v = get_val_at(target_sig, t, event_map, timestamps)
                        fmt_v = format_by_radix(raw_v, radix).upper()
                        if search_val in fmt_v or fmt_v.replace("0X", "") == search_val or fmt_v.replace("0B", "") == search_val:
                            found_time = t
                            break
                if found_time is not None:
                    time_offset = max(0, found_time - (center * zoom))
            elif key == ord('/'):
                if h > 3: stdscr.addstr(h-3, 0, "Filter text: ")
                curses.echo()
                filter_str = stdscr.getstr().decode('utf-8').strip()
                curses.noecho()
            if time_offset < 0: time_offset = 0

def main():
    if len(sys.argv) < 2:
        print("Error: Please provide a VCD file path.")
        print("Usage: kittywave <filename.vcd>  (or python view.py <filename.vcd>)")
        sys.exit(1)
        
    vcd_filename = sys.argv[1]
    try:
        signals, event_map, timestamps = parse_vcd(vcd_filename)
    except FileNotFoundError:
        print(f"Error: The file '{vcd_filename}' could not be found.")
        sys.exit(1)
        
    curses.wrapper(lambda stdscr: draw_viewer(stdscr, signals, event_map, timestamps))
if __name__ == "__main__":
    main()
