# human_typist.py
# Requires: pynput
# Run: python3 human_typist.py

import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import threading
import time
import random
import re
import string
from pynput.keyboard import Controller, Key, KeyCode
import sys

# ---------------- Typing engine helpers ----------------

keyboard = Controller()

ADJACENCY = {
    'a': ['s','q','w','z'],
    'b': ['v','g','h','n'],
    'c': ['x','d','f','v'],
    'd': ['s','e','r','f','c','x'],
    'e': ['w','s','d','r'],
    'f': ['d','r','t','g','v','c'],
    'g': ['f','t','y','h','b','v'],
    'h': ['g','y','u','j','n','b'],
    'i': ['u','j','k','o'],
    'j': ['h','u','i','k','m','n'],
    'k': ['j','i','o','l',',','m'],
    'l': ['k','o','p',';','.'],
    'm': ['n','j','k',','],
    'n': ['b','h','j','m'],
    'o': ['i','k','l','p'],
    'p': ['o','l',';','['],
    'q': ['w','a'],
    'r': ['e','d','f','t'],
    's': ['a','w','e','d','x','z'],
    't': ['r','f','g','y'],
    'u': ['y','h','j','i'],
    'v': ['c','f','g','b'],
    'w': ['q','a','s','e'],
    'x': ['z','s','d','c'],
    'y': ['t','g','h','u'],
    'z': ['a','s','x'],
}

SHIFT_CHARS = set(string.ascii_uppercase)
SHIFT_PUNCT = set('~!@#$%^&*()_+{}|:"<>?')

def human_sleep(mean_ms, sd_ms):
    t = max(10.0, random.gauss(mean_ms, sd_ms))
    time.sleep(t / 1000.0)

def press_char(ch, progress_callback=None):
    try:
        if ch == '\n':
            keyboard.press(Key.enter); keyboard.release(Key.enter)
            if progress_callback: progress_callback(1)
            return
        if ch == '\t':
            keyboard.press(Key.tab); keyboard.release(Key.tab)
            if progress_callback: progress_callback(1)
            return

        if ch in SHIFT_CHARS:
            keyboard.press(Key.shift)
            keyboard.press(KeyCode.from_char(ch.lower()))
            keyboard.release(KeyCode.from_char(ch.lower()))
            keyboard.release(Key.shift)
            if progress_callback: progress_callback(1)
            return

        try:
            keyboard.press(KeyCode.from_char(ch))
            keyboard.release(KeyCode.from_char(ch))
            if progress_callback: progress_callback(1)
            return
        except Exception:
            keyboard.type(ch)
            if progress_callback: progress_callback(len(ch))
            return
    except Exception:
        try:
            keyboard.type(ch)
            if progress_callback: progress_callback(len(ch))
        except Exception:
            pass

def backspace_n(n, progress_callback=None, speed_ms=12):
    for _ in range(n):
        keyboard.press(Key.backspace)
        keyboard.release(Key.backspace)
        if progress_callback: progress_callback(1)
        time.sleep(max(0.01, random.gauss(speed_ms, speed_ms*0.25)/1000.0))

def substitute_char(ch):
    low = ch.lower()
    if low in ADJACENCY and ADJACENCY[low]:
        choice = random.choice(ADJACENCY[low])
        return choice.upper() if ch.isupper() else choice
    return random.choice(string.ascii_lowercase) if random.random() < 0.05 else ch

def generate_typo_for_word(word, weights):
    strategies = list(weights.keys()); w = list(weights.values())
    strat = random.choices(strategies, w)[0]
    if len(word) == 0: return word
    if strat == 'sub':
        i = random.randrange(len(word))
        return word[:i] + substitute_char(word[i]) + word[i+1:]
    if strat == 'del':
        if len(word) == 1: return word
        i = random.randrange(len(word))
        return word[:i] + word[i+1:]
    if strat == 'ins':
        i = random.randrange(len(word)+1)
        add = random.choice(string.ascii_lowercase)
        return word[:i] + add + word[i:]
    if strat == 'trans':
        if len(word) < 2: return word
        i = random.randrange(len(word)-1)
        lst = list(word)
        lst[i], lst[i+1] = lst[i+1], lst[i]
        return ''.join(lst)
    return word

# ---------------- Pre-generate plan & pauses ----------------

def tokenize_keep_whitespace(text):
    return re.split(r'(\s+)', text)

def build_error_and_pause_plan(tokens, config):
    word_indices = [i for i,t in enumerate(tokens) if not re.fullmatch(r'\s+', t)]
    N_words = len(word_indices)
    word_error_rate = config['word_error_rate']
    char_error_rate = config['char_error_rate']
    error_weights = config['error_type_weights']

    plan = {i: {'whole_word_typo': None, 'char_errors': []} for i in range(len(tokens))}

    expected_seeds = round(word_error_rate * N_words) if N_words > 0 else 0
    seed_count = expected_seeds
    if N_words > 0 and random.random() < (word_error_rate * 0.3):
        seed_count = min(N_words, seed_count + 1)

    seed_choices = set()
    if seed_count > 0 and N_words > 0:
        seed_choices = set(random.sample(word_indices, min(seed_count, N_words)))

    for seed in sorted(seed_choices):
        plan[seed]['whole_word_typo'] = generate_typo_for_word(tokens[seed], error_weights)
        for direction in (-1, 1):
            if random.random() < 0.35:
                neighbor_pos = seed + direction
                if neighbor_pos in plan and not re.fullmatch(r'\s+', tokens[neighbor_pos]) and plan[neighbor_pos]['whole_word_typo'] is None:
                    plan[neighbor_pos]['whole_word_typo'] = generate_typo_for_word(tokens[neighbor_pos], error_weights)

    total_chars = sum(len(t) for t in tokens if not re.fullmatch(r'\s+', t))
    expected_char_errors = int(char_error_rate * total_chars)
    candidate_word_positions = [i for i in word_indices if plan[i]['whole_word_typo'] is None]
    if candidate_word_positions:
        for _ in range(expected_char_errors):
            if random.random() < 0.6 and seed_choices:
                seed = random.choice(list(seed_choices))
                offset = random.choice([-1,0,1])
                pos = seed + offset
                if pos in candidate_word_positions:
                    word = tokens[pos]
                    if len(word) > 0:
                        char_idx = random.randrange(len(word))
                        plan[pos]['char_errors'].append(char_idx)
                    continue
            pos = random.choice(candidate_word_positions)
            word = tokens[pos]
            if len(word) > 0:
                char_idx = random.randrange(len(word))
                plan[pos]['char_errors'].append(char_idx)

    for i in plan:
        plan[i]['char_errors'] = sorted(set(plan[i]['char_errors']))

    min_pw, max_pw = config.get('pause_word_interval', (3, 8))
    pauses = set()
    if N_words > 0:
        idx = 0
        while idx < N_words:
            step = random.randint(min_pw, max_pw)
            idx += step
            if idx >= N_words:
                break
            token_index = word_indices[max(0, idx-1)]
            pauses.add(token_index)
    return plan, pauses

# ---------------- Estimate time and count steps ----------------

def estimate_total_steps_and_seconds(tokens, plan, pauses, config):
    mean_ms = config['typing_speed_mean_ms']
    correction_mean = (config['correction_delay_range_ms'][0] + config['correction_delay_range_ms'][1]) / 2000.0
    pause_mean_s = (config.get('pause_duration_range_ms', (500, 1600))[0] + config.get('pause_duration_range_ms', (500, 1600))[1]) / 2000.0

    steps = 0
    for i, tok in enumerate(tokens):
        if re.fullmatch(r'\s+', tok):
            steps += len(tok)
        else:
            if plan[i]['whole_word_typo'] is not None:
                typo = plan[i]['whole_word_typo']
                correct = tok
                steps += len(typo) + len(typo) + len(correct)
            else:
                char_errs = plan[i]['char_errors']
                for idx, ch in enumerate(tok):
                    if idx in char_errs:
                        steps += 3
                    else:
                        steps += 1

    seconds_typing = steps * (mean_ms / 1000.0)
    num_word_errors = sum(1 for i in plan if plan[i]['whole_word_typo'] is not None)
    correction_waits = num_word_errors * correction_mean
    pause_count = len(pauses)
    pause_total = pause_count * pause_mean_s

    estimated_seconds = seconds_typing + correction_waits + pause_total
    return steps, estimated_seconds

# ---------------- Typing worker (uses precomputed plan) ----------------

def type_text_worker(tokens, plan, pauses, config, stop_event, progress_callback=None, on_finish_callback=None):
    """
    Types based on the *precomputed* tokens + plan + pauses.
    This guarantees the UI-estimate (based on the same plan) matches executed steps.
    """
    try:
        mean_ms = config['typing_speed_mean_ms']
        sd_ms = config['typing_speed_sd_ms']
        correction_range = config['correction_delay_range_ms']

        for i, token in enumerate(tokens):
            if stop_event.is_set(): break

            if re.fullmatch(r'\s+', token):
                for ch in token:
                    if stop_event.is_set(): break
                    press_char(ch, progress_callback)
                    human_sleep(mean_ms, sd_ms)
                continue

            if plan[i]['whole_word_typo'] is not None:
                typo = plan[i]['whole_word_typo']
                for ch in typo:
                    if stop_event.is_set(): break
                    press_char(ch, progress_callback)
                    human_sleep(mean_ms, sd_ms)
                if stop_event.is_set(): break
                time.sleep(random.uniform(correction_range[0], correction_range[1]) / 1000.0)
                backspace_n(len(typo), progress_callback)
                for ch in token:
                    if stop_event.is_set(): break
                    press_char(ch, progress_callback)
                    human_sleep(mean_ms, sd_ms)
            else:
                char_errs = set(plan[i]['char_errors'])
                for idx, ch in enumerate(token):
                    if stop_event.is_set(): break
                    if idx in char_errs and ch.isalpha():
                        typo_ch = substitute_char(ch)
                        press_char(typo_ch, progress_callback)
                        human_sleep(mean_ms/2, sd_ms/2)
                        backspace_n(1, progress_callback)
                        time.sleep(random.uniform(0.02, 0.12))
                    press_char(ch, progress_callback)
                    human_sleep(mean_ms, sd_ms)

            if i in pauses:
                pmin, pmax = config.get('pause_duration_range_ms', (500, 1600))
                pause_ms = random.randint(pmin, pmax)
                slept = 0.0
                step = 0.05
                while slept < pause_ms/1000.0:
                    if stop_event.is_set(): break
                    time.sleep(step)
                    slept += step
    finally:
        if on_finish_callback:
            try:
                on_finish_callback()
            except Exception:
                pass

# ---------------- GUI ----------------

class HumanTypistApp:
    def __init__(self, root):
        self.root = root
        root.title("Human-like Typist")
        root.geometry("700x560")
        root.resizable(False, False)
        try:
            root.attributes("-topmost", True)
            root.lift()
        except Exception:
            pass

        lbl = tk.Label(root, text="Text to type (paste here):", anchor="w")
        lbl.pack(fill='x', padx=10, pady=(10,0))

        self.text_input = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=86, height=18)
        self.text_input.pack(padx=10, pady=(0,10))

        controls = tk.Frame(root)
        controls.pack(fill='x', padx=10)

        sp_frame = tk.Frame(controls)
        sp_frame.pack(side='left', padx=6)
        tk.Label(sp_frame, text="Speed (ms/key)").pack()
        self.speed_scale = tk.Scale(sp_frame, from_=30, to=400, orient=tk.HORIZONTAL, length=220)
        self.speed_scale.set(120)
        self.speed_scale.pack()

        er_frame = tk.Frame(controls)
        er_frame.pack(side='left', padx=6)
        tk.Label(er_frame, text="Error rate (%)").pack()
        self.error_scale = tk.Scale(er_frame, from_=0, to=30, orient=tk.HORIZONTAL, length=220)
        self.error_scale.set(5)
        self.error_scale.pack()

        ps_frame = tk.Frame(controls)
        ps_frame.pack(side='left', padx=6)
        tk.Label(ps_frame, text="Pause every N words (min-max)").pack()
        self.pause_min = tk.Spinbox(ps_frame, from_=1, to=20, width=4)
        self.pause_min.delete(0, tk.END); self.pause_min.insert(0, "3")
        self.pause_min.pack(side='left')
        self.pause_max = tk.Spinbox(ps_frame, from_=1, to=40, width=4)
        self.pause_max.delete(0, tk.END); self.pause_max.insert(0, "8")
        self.pause_max.pack(side='left')

        dl_frame = tk.Frame(root)
        dl_frame.pack(fill='x', padx=10, pady=(6,0))
        tk.Label(dl_frame, text="Delay before start (s):").pack(side='left')
        self.delay_spin = tk.Spinbox(dl_frame, from_=0, to=30, width=5)
        self.delay_spin.delete(0, tk.END); self.delay_spin.insert(0, "3")
        self.delay_spin.pack(side='left', padx=(6,12))

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=12)
        self.start_btn = tk.Button(btn_frame, text="Start Typing", width=16, command=self.start_typing)
        self.start_btn.pack(side='left', padx=8)
        self.stop_btn = tk.Button(btn_frame, text="Stop", width=12, state=tk.DISABLED, command=self.stop_typing)
        self.stop_btn.pack(side='left', padx=8)

        prog_frame = tk.Frame(root)
        prog_frame.pack(fill='x', padx=10, pady=(6,10))
        tk.Label(prog_frame, text="Progress:").pack(anchor='w')
        self.progress = ttk.Progressbar(prog_frame, orient='horizontal', length=640, mode='determinate')
        self.progress.pack(pady=4)
        self.progress_label = tk.Label(prog_frame, text="0 / 0 (0%)")
        self.progress_label.pack(anchor='w')
        self.eta_label = tk.Label(prog_frame, text="Estimated: 00:00 | Elapsed: 00:00")
        self.eta_label.pack(anchor='w')

        self.typing_thread = None
        self.stop_event = threading.Event()
        self.total_steps = 1
        self.completed_steps = 0
        self.start_time = None
        self._topmost_job = None

    def start_typing(self):
        text = self.text_input.get("1.0", tk.END).rstrip('\n')
        if not text.strip():
            messagebox.showinfo("No text", "Please paste or type some text to be typed.")
            return

        typing_ms = int(self.speed_scale.get())
        pause_min = int(self.pause_min.get()); pause_max = int(self.pause_max.get())
        config = {
            'typing_speed_mean_ms': typing_ms,
            'typing_speed_sd_ms': max(5, int(typing_ms*0.25)),
            'word_error_rate': float(self.error_scale.get())/100.0,
            'char_error_rate': max(0.0, float(self.error_scale.get())/100.0 / 5.0),
            'correction_delay_range_ms': (150, 900),
            'error_type_weights': {'sub':0.55, 'del':0.15, 'ins':0.15, 'trans':0.15},
            'pause_word_interval': (pause_min, pause_max),
            'pause_duration_range_ms': (500, 1600),
        }

        # PREGENERATE tokens + plan + pauses ONCE (fixes progress mismatch)
        tokens = tokenize_keep_whitespace(text)
        plan, pauses = build_error_and_pause_plan(tokens, config)
        total_steps, estimated_seconds = estimate_total_steps_and_seconds(tokens, plan, pauses, config)

        # Setup progress UI
        self.total_steps = max(1, total_steps)
        self.completed_steps = 0
        self.progress['maximum'] = self.total_steps
        self.progress['value'] = 0
        self.progress_label.config(text=f"0 / {self.total_steps} (0%)")
        est_mm = int(estimated_seconds // 60); est_ss = int(estimated_seconds % 60)
        self.eta_label.config(text=f"Estimated: {est_mm:02d}:{est_ss:02d} | Elapsed: 00:00")

        self.stop_event.clear()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        try:
            delay = int(self.delay_spin.get())
        except Exception:
            delay = 3

        self.status_update(f"Starting in {delay} s... Focus the target window.")
        self._countdown_and_launch(delay, tokens, plan, pauses, config)

    def _ensure_topmost_loop(self):
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
        except Exception:
            pass
        if self.typing_thread and self.typing_thread.is_alive() and not self.stop_event.is_set():
            self._topmost_job = self.root.after(800, self._ensure_topmost_loop)
        else:
            self._topmost_job = None
            try:
                self.root.attributes("-topmost", True)
            except Exception:
                pass

    def _countdown_and_launch(self, delay, tokens, plan, pauses, config):
        if self.stop_event.is_set():
            self._enable_controls(); return
        if delay <= 0:
            self.status_update("Typing... (press Stop to cancel)")
            self.start_time = time.time()
            self._ensure_topmost_loop()
            # Pass tokens, plan, pauses into worker so worker uses same plan as UI
            self.typing_thread = threading.Thread(
                target=type_text_worker,
                args=(tokens, plan, pauses, config, self.stop_event, self._progress_callback_threadsafe, self._on_typing_finished),
                daemon=True
            )
            self.typing_thread.start()
            self._schedule_eta_update()
            return
        self.status_update(f"Starting in {delay} s... Focus the target window.")
        self.root.after(1000, lambda: self._countdown_and_launch(delay-1, tokens, plan, pauses, config))

    def stop_typing(self):
        self.stop_event.set()
        self.status_update("Stopping...")
        if self._topmost_job:
            try:
                self.root.after_cancel(self._topmost_job)
            except Exception:
                pass
            self._topmost_job = None
        self.root.after(300, self._enable_controls)

    def _on_typing_finished(self):
        def finish_ui():
            try:
                self.root.attributes("-topmost", True)
            except Exception:
                pass
            self.status_update("Idle")
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self._update_eta_display(force=True)
        self.root.after(50, finish_ui)

    def _enable_controls(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_update("Idle")

    def status_update(self, text):
        try:
            self.status_label_text = text
        except Exception:
            pass
        self.root.title(f"Human-like Typist — {text}")

    def _progress_callback_threadsafe(self, delta_steps):
        self.root.after(10, lambda: self._progress_update(delta_steps))

    def _progress_update(self, delta_steps):
        self.completed_steps += delta_steps
        if self.completed_steps > self.total_steps:
            self.completed_steps = self.total_steps
        self.progress['value'] = self.completed_steps
        pct = int((self.completed_steps / self.total_steps) * 100)
        self.progress_label.config(text=f"{self.completed_steps} / {self.total_steps} ({pct}%)")

    def _schedule_eta_update(self):
        if self.typing_thread is None or not self.typing_thread.is_alive():
            return
        self._update_eta_display()
        self.root.after(500, self._schedule_eta_update)

    def _update_eta_display(self, force=False):
        if not self.start_time:
            return
        elapsed = time.time() - self.start_time
        frac = (self.completed_steps / self.total_steps) if self.total_steps else 0.0
        if frac <= 0:
            est_total = None
        else:
            est_total = elapsed / frac
        if est_total is None:
            eta_text = "Estimated: --:--"
        else:
            rem = max(0.0, est_total - elapsed)
            est_mm = int((est_total) // 60); est_ss = int(est_total % 60)
            rem_mm = int(rem // 60); rem_ss = int(rem % 60)
            eta_text = f"Estimated total: {est_mm:02d}:{est_ss:02d} | Remaining: {rem_mm:02d}:{rem_ss:02d}"
        elapsed_mm = int(elapsed // 60); elapsed_ss = int(elapsed % 60)
        self.eta_label.config(text=f"{eta_text} | Elapsed: {elapsed_mm:02d}:{elapsed_ss:02d}")

def main():
    root = tk.Tk()
    app = HumanTypistApp(root)
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
