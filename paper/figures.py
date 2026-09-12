"""Build every figure used in the paper from results/ only. Run with .venv-body (matplotlib lives there)."""
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results"
FIG = Path(__file__).resolve().parent / "figures"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 170})
INK = "#1a1a1a"
BLUE, ORANGE, GREEN, RED, GREY = "#2c6fbb", "#e08a1e", "#3a9e57", "#c0392b", "#8a8a8a"


def load(path):
    return json.loads((R / path).read_text())


# ---------------------------------------------------------------- fig 1: architecture
def fig_architecture(lang):
    T = {"ru": dict(title="Единая цепочка управления: сменный только один блок",
                    boxes=["Два локальных\nсенсорных канала", "Сменный модуль\nвыбора действия", "Общий адаптер\nкоманд", "Штатный контроллер ходьбы\n(CPG и рефлексы)", "Тело мухи\nв физическом движке"],
                    variants=["A — постоянная команда", "B — простое правило", "C — коннектом мухи", "D — запись из другого эпизода", "E — перемешанный коннектом"],
                    inner=["щетинки\nголовы L/R", "сеть 138 639\nнейронов, 15 мс", "разность спайков\nнисходящих L−R"],
                    caption="Внутри мозгового варианта", cmd="скорость, поворот", tick="каждые 15 мс"),
         "en": dict(title="One shared control chain; only a single block is swapped",
                    boxes=["Two local\nsensory channels", "Swappable action\nselection module", "Shared command\nadapter", "Stock walking controller\n(CPG + reflexes)", "Fly body\nin the physics engine"],
                    variants=["A — constant command", "B — simple rule", "C — fly connectome", "D — replay from another episode", "E — shuffled connectome"],
                    inner=["head bristles\nL/R", "network of 138,639\nneurons, 15 ms", "descending spike\ndifference L−R"],
                    caption="Inside the brain variant", cmd="speed, turn", tick="every 15 ms")}[lang]
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.set_xlim(0, 100); ax.set_ylim(0, 62); ax.axis("off")
    xs = [1, 20, 40, 56, 80]
    ws = [17, 18, 13, 22, 19]
    colors = ["#eef3fa", "#fdf0dd", "#eef3fa", "#eef3fa", "#eef3fa"]
    for x, w, t, c in zip(xs, ws, T["boxes"], colors):
        ax.add_patch(FancyBboxPatch((x, 44), w, 12, boxstyle="round,pad=0.6", fc=c, ec=INK, lw=.8))
        ax.text(x + w / 2, 50, t, ha="center", va="center", fontsize=7.4)
    for x, w in zip(xs[:-1], ws[:-1]):
        nxt = xs[xs.index(x) + 1]
        ax.add_patch(FancyArrowPatch((x + w, 50), (nxt, 50), arrowstyle="-|>", mutation_scale=9, lw=.9, color=INK))
    ax.text((xs[2] + ws[2] / 2), 57.8, T["cmd"], ha="center", fontsize=7.5, style="italic", color=GREY)
    ax.text(50, 41, T["tick"], ha="center", fontsize=7.5, style="italic", color=GREY)
    # variants
    for i, v in enumerate(T["variants"]):
        y = 33 - i * 5.6
        ax.add_patch(FancyBboxPatch((1, y), 24, 4.4, boxstyle="round,pad=0.3", fc="#ffffff", ec=ORANGE if i == 2 else "#c9c9c9", lw=1.3 if i == 2 else .7))
        ax.text(13, y + 2.2, v, ha="center", va="center", fontsize=7.2, color=INK if i == 2 else "#444")
    ax.add_patch(FancyArrowPatch((26, 46), (20, 35.4), arrowstyle="-|>", mutation_scale=8, lw=.8, color="#999", linestyle=":"))
    # inside the brain variant
    ax.add_patch(FancyBboxPatch((37, 3), 62, 25, boxstyle="round,pad=0.6", fc="#fffaf2", ec=ORANGE, lw=.9))
    ax.text(68, 24.5, T["caption"], ha="center", fontsize=8, color=ORANGE)
    ix = [40, 60, 80]
    for x, t in zip(ix, T["inner"]):
        ax.add_patch(FancyBboxPatch((x, 8), 17, 11, boxstyle="round,pad=0.5", fc="#ffffff", ec=INK, lw=.7))
        ax.text(x + 8.5, 13.5, t, ha="center", va="center", fontsize=7.2)
    for x in ix[:-1]:
        ax.add_patch(FancyArrowPatch((x + 17, 13.5), (x + 20, 13.5), arrowstyle="-|>", mutation_scale=8, lw=.9, color=INK))
    ax.add_patch(FancyArrowPatch((25, 24.5), (36, 20), arrowstyle="-|>", mutation_scale=8, lw=.9, color=ORANGE, linestyle=":"))
    ax.set_title(T["title"], fontsize=10, loc="left")
    fig.tight_layout(); fig.savefig(FIG / f"fig1-architecture-{lang}.png", bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------- fig 2: A/B/C/D/E success
def fig_results(lang):
    ab = load("ab-test-v1/summary.json")
    cda = load("cd-test-v1/compare-C-vs-A-ab-test-v1/summary.json")
    cd = load("cd-test-v1/summary.json")
    ef = load("e-compare-fixed-v1/summary.json")
    er = load("e-compare-recal-v1/summary.json")
    scen = ["none", "left", "right"]
    T = {"ru": dict(x=["нет стимула", "стимул слева", "стимул справа"],
                    series=["A: постоянная\nкоманда", "B: простое\nправило", "C: коннектом", "D: запись из\nдругого эпизода", "E: перемешанные\nсети (среднее)"],
                    ylabel="доля успешных эпизодов из 30\n(подписи — число успехов)", title="Четыре варианта управления на одних и тех же событиях",
                    note="E — среднее по пяти перемешанным сетям с перекалиброванным считыванием; вертикальные штрихи — разброс между сетями"),
         "en": dict(x=["no stimulus", "stimulus left", "stimulus right"],
                    series=["A: constant\ncommand", "B: simple\nrule", "C: connectome", "D: replay from\nanother episode", "E: shuffled\nnetworks (mean)"],
                    ylabel="fraction of 30 episodes solved\n(labels give the count)", title="Four control variants on identical events",
                    note="E is the mean over five shuffled networks with a recalibrated readout; whiskers show the spread across networks")}[lang]
    A = [ab[s]["A_successes"] / 30 for s in scen]
    B = [ab[s]["B_successes"] / 30 for s in scen]
    C = [cd[s]["C_successes"] / 30 for s in scen]
    D = [cd[s]["D_successes"] / 30 for s in scen]
    Enets = {s: [n["E_successes"] / 30 for n in er[s]["networks"].values()] for s in scen}
    E = [np.mean(Enets[s]) for s in scen]
    Eerr = [[E[i] - min(Enets[s]) for i, s in enumerate(scen)], [max(Enets[s]) - E[i] for i, s in enumerate(scen)]]
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    w = .16
    pos = np.arange(3)
    for k, (vals, col, lab) in enumerate(zip([A, B, C, D, E], [GREY, GREEN, BLUE, RED, "#9b59b6"], T["series"])):
        x = pos + (k - 2) * w
        err = Eerr if k == 4 else None
        ax.bar(x, vals, w, color=col, label=lab, yerr=err, capsize=2.5, error_kw=dict(lw=.8, ecolor="#444"))
        for xi, v in zip(x, vals):
            if v == 0:  # a zero bar is invisible; mark it so the reader sees the variant failed, not that it is missing
                ax.plot([xi - w / 2.4, xi + w / 2.4], [0, 0], color=col, lw=2.4, solid_capstyle="butt")
            ax.text(xi, max(v, 0) + (.09 if k == 4 else .035), f"{v * 30:.0f}" if k != 4 else f"{v * 30:.0f}", ha="center", fontsize=6.6, color="#333")
    ax.set_xticks(pos); ax.set_xticklabels(T["x"]); ax.set_ylim(-.02, 1.18); ax.set_ylabel(T["ylabel"])
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.legend(fontsize=7, ncol=5, loc="upper center", frameon=False, bbox_to_anchor=(.5, -.12))
    ax.set_title(T["title"], fontsize=10, loc="left")
    ax.text(0, -.36, T["note"], fontsize=7, color=GREY, transform=ax.transAxes)
    fig.tight_layout(); fig.savefig(FIG / f"fig2-results-{lang}.png", bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------- fig 3: descending output, original vs shuffled
def fig_descending(lang):
    T = {"ru": dict(title="Что видит считывание: разность спайков левых и правых нисходящих нейронов",
                    ylabel="L − R за такт 15 мс", xlabel="время эпизода, с",
                    lab=["коннектом, стимул слева", "коннектом, стимул справа", "перемешанная сеть, стимул слева", "перемешанная сеть, стимул справа"],
                    stim="стимул включён", note="Один эпизод каждого типа, seed 2000. У настоящей сети знак разности повторяет сторону стимула; у перемешанной сигнал почти исчезает."),
         "en": dict(title="What the readout sees: spike difference between left and right descending neurons",
                    ylabel="L − R per 15 ms tick", xlabel="episode time, s",
                    lab=["connectome, stimulus left", "connectome, stimulus right", "shuffled network, stimulus left", "shuffled network, stimulus right"],
                    stim="stimulus on", note="One episode of each type, seed 2000. In the real network the sign of the difference follows the stimulated side; in the shuffled one the signal all but vanishes.")}[lang]
    fig, ax = plt.subplots(figsize=(7.4, 3.2))
    for tag, side, col, ls, lab in (("c-brain-test-v1", "left", BLUE, "-", T["lab"][0]), ("c-brain-test-v1", "right", ORANGE, "-", T["lab"][1]),
                                    ("e-brain-test-v1-s4000", "left", BLUE, ":", T["lab"][2]), ("e-brain-test-v1-s4000", "right", ORANGE, ":", T["lab"][3])):
        d = load(f"{tag}-{side}-2000/brain_ticks.json")["ticks"]
        t = [x["t_end_s"] for x in d]
        y = [x["DN_left"] - x["DN_right"] for x in d]
        ax.plot(t, y, ls, color=col, lw=1.3, label=lab)
    onset = next(x["t_end_s"] for x in load("c-brain-test-v1-left-2000/brain_ticks.json")["ticks"] if x["input_left"])
    ax.axvspan(onset, 1.005, color="#f2f2f2", zorder=0)
    ax.text(onset + .02, ax.get_ylim()[0] * .82, T["stim"], fontsize=7.5, color=GREY)
    ax.axhline(0, color="#bbb", lw=.7)
    ax.set_xlabel(T["xlabel"]); ax.set_ylabel(T["ylabel"]); ax.legend(fontsize=7, frameon=False, ncol=2, loc="upper right")
    ax.set_title(T["title"], fontsize=10, loc="left")
    ax.text(0, -.3, T["note"], fontsize=7, color=GREY, transform=ax.transAxes, wrap=True)
    fig.tight_layout(); fig.savefig(FIG / f"fig3-descending-{lang}.png", bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------- fig 4: video frames
def fig_frames(lang):
    import imageio.v2 as imageio
    T = {"ru": dict(title="Кадры контрольных роликов варианта C (коннектом), тестовые seeds",
                    rows=["стимул слева, seed 2000", "стимул справа, seed 2001", "без стимула, seed 2002"],
                    note="Камера следует за курсом мухи, поэтому поворот заметнее по смене фона, чем по развороту тела."),
         "en": dict(title="Frames from the control videos of variant C (connectome), test seeds",
                    rows=["stimulus left, seed 2000", "stimulus right, seed 2001", "no stimulus, seed 2002"],
                    note="The camera follows the fly's heading, so a turn shows up in the background rather than as body rotation.")}[lang]
    specs = [("video-left-C-2000", T["rows"][0]), ("video-right-C-2001", T["rows"][1]), ("video-none-C-2002", T["rows"][2])]
    picks = [10, 60, 110, 160, 210]
    fig, axes = plt.subplots(3, len(picks), figsize=(7.4, 3.9))
    for r, (tag, label) in enumerate(specs):
        rd = imageio.get_reader(R / tag / "body.mp4")
        frames = {i: f for i, f in enumerate(rd) if i in picks}
        rd.close()
        for c, p in enumerate(picks):
            ax = axes[r, c]
            ax.imshow(frames[min(frames, key=lambda k: abs(k - p))])
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_visible(False)
            if r == 0:
                ax.set_title(f"{p / 30:.1f} s", fontsize=7, color=GREY)
        axes[r, 0].set_ylabel(label, fontsize=7, rotation=0, ha="right", va="center", labelpad=6)
    fig.suptitle(T["title"], fontsize=10, x=.02, ha="left")
    fig.text(.02, .01, T["note"], fontsize=7, color=GREY)
    fig.tight_layout(rect=[0, .03, 1, .95]); fig.savefig(FIG / f"fig4-frames-{lang}.png", bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------- fig 5: sensory screen
def fig_screen(lang):
    NAMES = {"ru": {"head bristle": "щетинки головы", "sugar/water": "сахар и вода", "bitter": "горькое", "taste peg": "вкусовые сосочки",
                    "low-salt": "слабосолёное", "grooming": "щетинки чистки", "wind_gravity": "ветер и гравитация", "auditory": "слух",
                    "accessory_pharyngeal_nerve_sensory_group1": "глоточные рецепторы", "dry": "сухость", "moist": "влажность", "cooling": "испарительное охлаждение",
                    "cold": "холод", "heating": "тепло", "humid": "влажный воздух", "pheromone": "феромоны", "DRA": "поляризованный свет"},
             "en": {"head bristle": "head bristles", "sugar/water": "sugar and water", "bitter": "bitter", "taste peg": "taste pegs",
                    "low-salt": "low salt", "grooming": "grooming bristles", "wind_gravity": "wind and gravity", "auditory": "hearing",
                    "accessory_pharyngeal_nerve_sensory_group1": "pharyngeal receptors", "dry": "dryness", "moist": "moisture", "cooling": "evaporative cooling",
                    "cold": "cold", "heating": "warmth", "humid": "humid air", "pheromone": "pheromones", "DRA": "polarised light"}}[lang]
    T = {"ru": dict(title="Поиск входа: отклик поворотных нейронов DNa02 на разные органы чувств",
                    xlabel="частота DNa02 на стороне стимула, Гц (слева — вход слева, справа — вход справа)",
                    legend=["ответ без лавины", "лавина: сеть уходит в одно и то же состояние при любом входе"],
                    note="Каждая пара полос — один класс рецепторов, 150 Гц, одна секунда. Годится только вход, дающий зеркальный ответ без лавины: это щетинки головы."),
         "en": dict(title="Finding an input: how the DNa02 steering neurons respond to different sense organs",
                    xlabel="DNa02 rate on the stimulated side, Hz (left bar = left input, right bar = right input)",
                    legend=["response without an avalanche", "avalanche: the network falls into the same state for any input"],
                    note="Each pair of bars is one receptor class at 150 Hz for one second. Only an input with a mirrored, avalanche-free response qualifies: the head bristles.")}[lang]
    import csv
    rows = [r for r in csv.DictReader((R / "screen783-analysis/runs.csv").open()) if "pulse" not in r["label"] and float(r["hz"]) == 150]
    classes = []
    for r in rows:
        key = (r["cell_class"], r["sub_class"])
        if key not in classes:
            classes.append(key)
    def cell(key, side):
        m = [r for r in rows if (r["cell_class"], r["sub_class"]) == key and r["side"] == side]
        if not m:
            return None
        r = m[0]
        return float(r["DNa02L"] if side == "left" else r["DNa02R"]), r["avalanche"] == "True"
    order = sorted(classes, key=lambda k: -(max((cell(k, s) or (0, 0))[0] for s in ("left", "right"))))
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    h = .36
    for i, key in enumerate(order):
        y = len(order) - i
        for j, side in enumerate(("left", "right")):
            c = cell(key, side)
            if c is None:
                continue
            val, aval = c
            ax.barh(y + (.5 - j) * h, val, h * .92, color=RED if aval else GREEN, alpha=.9)
            if val == 0:
                ax.plot([0, .35], [y + (.5 - j) * h] * 2, color="#c9c9c9", lw=2.4, solid_capstyle="butt")
    ax.set_yticks([len(order) - i for i in range(len(order))])
    dup = {k[1] for k in order if sum(1 for j in order if j[1] == k[1]) > 1}
    qual = {"ru": {"gustatory": " (вкус)", "mechanosensory": " (механо)"}, "en": {"gustatory": " (taste)", "mechanosensory": " (touch)"}}[lang]
    ax.set_yticklabels([NAMES.get(k[1], k[1]) + (qual.get(k[0], "") if k[1] in dup else "") for k in order], fontsize=7.6)
    for lbl, k in zip(ax.get_yticklabels(), order):
        if k[1] == "head bristle":
            lbl.set_fontweight("bold")
    ax.set_xlabel(T["xlabel"], fontsize=8)
    ax.set_title(T["title"], fontsize=10, loc="left")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=GREEN, label=T["legend"][0]), Patch(color=RED, label=T["legend"][1])], fontsize=7, frameon=False, loc="lower right", bbox_to_anchor=(1, .04))
    ax.text(0, -.16, T["note"], fontsize=7, color=GREY, transform=ax.transAxes)
    fig.tight_layout(); fig.savefig(FIG / f"fig5-screen-{lang}.png", bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------- fig 6: trajectories
def fig_traj(lang):
    T = {"ru": dict(title="Траектории тела на одних и тех же событиях, seed 2000 и 2001",
                    panels=["стимул слева", "стимул справа"], xlabel="x, мм", ylabel="y, мм",
                    lab={"A": "A: постоянная команда", "B": "B: простое правило", "C": "C: коннектом", "D": "D: запись из другого эпизода", "E": "E: перемешанная сеть"},
                    start="старт",
                    note="Кружок отмечает момент включения стимула. Правило и коннектом дают почти совпадающие траектории (зелёная линия скрыта под синей). Перемешанная сеть уводит муху влево независимо от стороны стимула: слева это случайно засчитывается как успех, справа — очевидный провал."),
         "en": dict(title="Body trajectories on identical events, seeds 2000 and 2001",
                    panels=["stimulus left", "stimulus right"], xlabel="x, mm", ylabel="y, mm",
                    lab={"A": "A: constant command", "B": "B: simple rule", "C": "C: connectome", "D": "D: replay from another episode", "E": "E: shuffled network"},
                    start="start",
                    note="The circle marks stimulus onset. The rule and the connectome trace almost the same path (the green line hides under the blue). The shuffled network veers left whatever the stimulated side: on the left that accidentally counts as success, on the right it plainly fails.")}[lang]
    import csv
    panels = [("left", 2000), ("right", 2001)]
    cols = {"A": GREY, "B": GREEN, "C": BLUE, "D": RED, "E": "#9b59b6"}
    widths = {"B": 3.4, "C": 1.5}
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.8), sharex=True, sharey=True)
    for ax, (side, seed) in zip(axes, panels):
        src = {"A": f"ab-test-v1-{side}-A-{seed}", "B": f"ab-test-v1-{side}-B-{seed}", "C": f"cd-test-v1-{side}-C-{seed}",
               "D": f"cd-test-v1-{side}-D-{seed}", "E": f"e-recal-test-v1-s4000-{side}-E-{seed}"}
        for k, tag in src.items():
            rows = list(csv.DictReader((R / tag / "trajectory.csv").open()))
            x = [float(r["x_mm"]) for r in rows]
            y = [float(r["y_mm"]) for r in rows]
            ax.plot(x, y, color=cols[k], lw=widths.get(k, 1.6), alpha=.55 if k == "B" else 1, label=T["lab"][k], zorder=3 if k in "BC" else 2)
            onset = json.loads((R / tag / "events.json").read_text())["onset_tick"]
            ax.plot(x[onset], y[onset], "o", color=cols[k], ms=3.5, zorder=4)
        ax.plot(0, 0, "k+", ms=7)
        ax.set_title(f"{T['panels'][panels.index((side, seed))]}, seed {seed}", fontsize=8.5)
        ax.set_xlabel(T["xlabel"]); ax.set_aspect("equal", adjustable="box")
    axes[0].set_ylabel(T["ylabel"])
    axes[0].legend(fontsize=6.8, frameon=False, loc="upper left")
    fig.suptitle(T["title"], fontsize=10, x=.02, ha="left")
    fig.text(.02, -.04, T["note"], fontsize=7, color=GREY, wrap=True)
    fig.tight_layout(rect=[0, 0, 1, .95]); fig.savefig(FIG / f"fig6-trajectories-{lang}.png", bbox_inches="tight"); plt.close(fig)



# ---------------------------------------------------------------- fig 7: SAT decodability
def fig_decode(lang):
    T = {"ru": dict(title="Сколько информации о задаче доходит до нисходящих нейронов за один такт",
                    bits=["значение\nпеременной", "«+» в невыполненной\nклаузе", "«−» в невыполненной\nклаузе"],
                    series=["коннектом мухи", "перемешанный (степени сохранены)", "случайная топология"],
                    ylabel="точность линейного декодера", chance="случайный уровень",
                    note="Декодер обучен восстанавливать входные биты по спайкам 1299 нисходящих нейронов за 15 мс. Это измерение проводимости сети, а не её вычислительной силы."),
         "en": dict(title="How much task information reaches the descending neurons in a single tick",
                    bits=["variable\nvalue", "“+” in an unsatisfied\nclause", "“−” in an unsatisfied\nclause"],
                    series=["fly connectome", "shuffled (degrees preserved)", "random topology"],
                    ylabel="linear decoder accuracy", chance="chance level",
                    note="The decoder is trained to recover the input bits from the spikes of 1,299 descending neurons in 15 ms. This measures the network's conduction, not its computational power.")}[lang]
    kinds = [("fly", BLUE), ("fly-shuffled", "#9b59b6"), ("fly-random", GREY)]
    data = {}
    for k, _ in kinds:
        d = json.loads((R / f"sat-fly/decodability-{k}-s0.json").read_text())[k]["decoding"]["current"]
        data[k] = d
    bits = ["value", "pos_in_unsat", "neg_in_unsat"]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    w = .24
    pos = np.arange(3)
    for i, (k, col) in enumerate(kinds):
        vals = [data[k][b]["test_accuracy"] for b in bits]
        ax.bar(pos + (i - 1) * w, vals, w, color=col, label=T["series"][i])
        for x, v in zip(pos + (i - 1) * w, vals):
            ax.text(x, v + .015, f"{v * 100:.0f}", ha="center", fontsize=7)
    ch = [np.mean([data[k][b]["majority_class_rate"] for k, _ in kinds]) for b in bits]
    for x, c in zip(pos, ch):
        ax.plot([x - 1.6 * w, x + 1.6 * w], [c, c], color=RED, lw=1, ls="--")
    ax.text(pos[-1] + 1.7 * w, ch[-1], T["chance"], fontsize=7, color=RED, va="center")
    ax.set_xticks(pos); ax.set_xticklabels(T["bits"], fontsize=8); ax.set_ylim(0, 1.12)
    ax.set_ylabel(T["ylabel"]); ax.set_yticks([0, .25, .5, .75, 1])
    ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(.5, -.14))
    ax.set_title(T["title"], fontsize=10, loc="left")
    ax.text(0, -.38, T["note"], fontsize=7, color=GREY, transform=ax.transAxes)
    fig.tight_layout(); fig.savefig(FIG / f"fig7-decodability-{lang}.png", bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    for lang in ("ru", "en"):
        fig_architecture(lang); fig_results(lang); fig_descending(lang); fig_screen(lang); fig_traj(lang); fig_decode(lang)
        try:
            fig_frames(lang)
        except Exception as exc:
            print("frames failed:", exc)
    print("figures:", sorted(p.name for p in FIG.glob("*.png")))
