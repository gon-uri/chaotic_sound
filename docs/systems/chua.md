<!-- Draft written by an AI agent; facts need human review before publishing. Last updated: 2026-10-26 -->

# Chua's circuit

> Five electronic parts, sketched on napkins one evening in 1983, that helped show chaos is a real, physical thing and not a computer glitch.

## In plain words

Most systems on this synth began as equations. Chua's began as a design for a real electronic circuit: two capacitors, a coil, a resistor and one odd part, "Chua's diode". Ordinary parts only soak up energy; this one, powered by a battery, pumps energy back in. The voltages start to swirl, the swirl grows, and at some point it is flung across to a mirror-image swirl, and back again, never twice the same way.

Plotted in 3D, the motion draws two spirals side by side: the **double scroll**. Think of a reedy buzz that holds its note but every so often flips upside down at moments nobody can predict. Turn the knob down and the flips stop: the circuit circles a single scroll, a steadier, more tonal buzz.

## Equations

$$
\begin{aligned}
\dot{x} &= \alpha\,\bigl(y - x - h(x)\bigr)\\
\dot{y} &= x - y + z\\
\dot{z} &= -\beta\,y\\
h(x) &= m_1 x + \tfrac{1}{2}(m_0 - m_1)\bigl(|x+1| - |x-1|\bigr)
\end{aligned}
$$

- $x$, $y$: voltages across the capacitors $C_1$ (wired across the diode) and $C_2$, divided by the diode's breakpoint voltage $E$; $z = R\,i_L/E$: the current through the inductor $L$, in units of $E/R$. Time is in units of $RC_2$ (the usual normalization).
- $\alpha = C_2/C_1 = 15.6$ and $\beta = C_2R^2/L = 28$: ratios of component values (dysts' setting; in the app $\alpha$ is the knob, with default 15.8).
- $h(x)$: Chua's diode, three straight segments with slope $m_0 = -8/7 \approx -1.143$ for $|x|<1$ and $m_1 = -5/7 \approx -0.714$ outside. Both slopes are negative: a "negative resistance".
- The $y - x$ term in $\dot{x}$ (and $x - y$ in $\dot{y}$) is the current through the ordinary resistor $R$ that couples the two capacitors.

**dysts compared with the original.** Chua, Komuro and Matsumoto [5] fold the $-x$ part of the resistor current into the diode, writing $\dot{x} = \alpha\,(y - \tilde h(x))$ with $\tilde h = x + h$, so their slopes are $m_0+1 = -1/7$ and $m_1+1 = 2/7$; their classic double-scroll point is $\alpha = 9$, $\beta = 100/7$. dysts [18] uses a different, commonly used setting, $\alpha = 15.6$, $\beta = 28$, with the slopes rounded. The figures in Scholarpedia [6], taken from Alligood, Sauer and Yorke [9], use the same $\alpha$, $m_0$ and $m_1$ and vary $\beta$. A real diode has five segments, not three: its outer segments turn passive and keep the voltages bounded [1, 7].

## The parameter you control

The knob sets $\alpha = C_2/C_1$; raising it is like shrinking $C_1$. The sequence at $\beta = 28$ is below; values under 13.7 and the window near 13.9 come from our own simulations and eigenvalue calculations (independent runs agree), not yet checked against the literature.

| $\alpha$ | What happens |
|---|---|
| below ≈10.1 | Motion settles on one of the two outer equilibria: silence. |
| ≈10.1 | They lose stability (Hopf-type) and an oscillation is born around each. |
| ≈13.15–13.7 | Period doubling: period 2 from ≈13.15, period 4 near 13.6, period 8 near 13.68, then chaos. |
| 13.7–14.43 | Two mirror-image **single-scroll** (Rössler-like) chaotic attractors, with narrow periodic windows (near 13.9 and 14.1). |
| ≈14.43 | The twins touch and merge into the **double scroll** (attractor-merging crisis). |
| up to ≈18.4 | Double scroll, with narrow periodic windows. |
| ≈18.45 | In the three-segment model, trajectories escape to infinity. |

Kennedy saw the same story on a breadboard by tuning a single component: equilibrium, Hopf, periods 1, 2 and 4, a Rössler-type attractor, a period-3 window, the double scroll and finally a large limit cycle on the diode's outer segments [7]. Rodet *heard* the cascade with the parameter values of Chua, Komuro and Matsumoto [5] ($\beta = 100/7$, folded slopes $-1/7$ and $2/7$; his printed equations keep the $-x$ term, but he compares with their parameter map). In his real-time Euler simulation, $\alpha$ = 8.0, 8.2 and 8.24 gave harmonic tones of period 1, 2 and 4, the fundamental halving each time [10]. He notes that his simple simulation differs a little from theory; our accurate integration puts period 4 near $\alpha \approx 8.4$.

## Properties

- **Attractor:** two interleaved spirals; Kaplan–Yorke dimension ≈ 2.11 (dysts, at $\alpha = 15.6$).
- **Equilibria:** the origin and $P^\pm = (\pm 1.5, 0, \mp 1.5)$, all unstable at the default ($\alpha = 15.8$), as Chua designed [1]. $P^\pm$ are saddle-foci (eigenvalues $\approx 0.31 \pm 4.53i$, $-6.14$): trajectories spiral outward until thrown across the middle.
- **Piecewise linear:** in each slab ($x<-1$, $|x|<1$, $x>1$) the equations are linear and exactly solvable, which made a proof possible [5, 6].
- **Symmetry:** $(x,y,z)\mapsto(-x,-y,-z)$.
- **Dissipation:** the divergence is $\alpha/7 - 1$ in the middle slab (≈ +1.26 at the default: volumes grow) and $-2\alpha/7 - 1$ outside (≈ −5.51); on average volumes shrink (dysts' exponents, at $\alpha = 15.6$, sum to ≈ −3.86).
- **Lyapunov exponents:** we measure $\lambda \approx 0.40$ at the default and ≈ 0.43 at dysts' value 15.6. There dysts' spectrum, $(0.46, 0.00, -4.32)$, roughly agrees; its separate largest-exponent estimate, 1.23, is higher. Since $\lambda P \approx 0.59$ at the default, nearby states drift apart almost twofold per cycle ($e^{0.59} \approx 1.8$).
- **Phase coherence:** partial. The spin around each scroll is fairly regular, with a period of about 1.4–1.7 time units across the knob's range (1.45 at the default; the linear estimate at $P^\pm$, $2\pi/4.53 \approx 1.39$, is slightly low). The hops between scrolls are irregular. $y$ is centred on 0 at every equilibrium, so the hops disturb it much less than $x$, which jumps between about ±1.5.
- **Boundedness:** the three-segment model is not globally bounded; a physical circuit is.

## History

**One evening in Tokyo.** Leon O. Chua (born 1936 in the Philippines, a UC Berkeley professor since the early 1970s, also known for predicting the memristor [16]) arrived in Tokyo in late October 1983 for a fellowship. The next day he visited Takashi Matsumoto's lab at Waseda University to see what was meant to be the first electronic circuit obeying the Lorenz equations. After more than a year of work, it failed: the analog multipliers it needed were not good enough [1].

That night Chua reasoned that the Lorenz and Rössler systems both owe their chaos to at least two unstable equilibria. In under an hour he listed eight candidate circuits and narrowed them to one, scribbling on napkins and envelopes because his new dormitory had no paper. Next morning Matsumoto programmed it (in BASIC) and soon found a strange attractor [1]. He published it in December 1984 and named it "Chua's circuit" [2].

**Seen, built, proven.** Matsumoto's group had held off building the circuit, so Chua asked G.-Q. Zhong and F. Ayrom in Berkeley. Their breadboard worked with almost no tuning [1, 3]. The 1985 paper "The double scroll" described the attractor in detail [4]. In 1986 Chua, Komuro and Matsumoto exploited the piecewise-linear structure to prove that, for certain parameter values (not necessarily the ones used in this app), the circuit has chaotic dynamics in the sense of Shil'nikov's theorem [5]. Chaos had now been seen in simulation, in the lab and in a proof. In 1993 Kennedy called it the only physical system for which chaos had been proved mathematically [8]. The Lorenz attractor had to wait until Warwick Tucker's computer-assisted proof of 1999 [6, 19].

**Influence.** Kennedy's version uses two op-amps and off-the-shelf parts [7]. The circuit itself entered textbooks such as Alligood, Sauer and Yorke's *Chaos* (§9.4) [9], and a 1993 book called it "a paradigm for chaos" [17].

**Sound and music.** In the early 1990s at Berkeley's CNMAT, Xavier Rodet (IRCAM) simulated it in real time and listened: periodic regimes gave harmonic tones, chaos gave noise mixed with harmonics. A time-delayed version modelled clarinet-like instruments [10, 11]. He notes that David Wessel used its output to drive pitch, duration and dynamics [10]. Mayer-Kress and colleagues [12], Zhong, Bargar and Halle (voltage-controlled tuning for live use) [13], Choi (real-time concert performance) [14] and Bilotta and colleagues [15] followed.

## In chaotic_sound

Numbers are in the system's own time units.

- **What you hear:** by default $y$, the most pitched variable. The app finds $y$'s strongest spectral peak and takes its period $P$ at the peak's power-weighted centre (the "peak centroid"). A chaotic peak is broad and lumpy; the centroid averages over the lumps, so it is steadier than the single highest point. Your note is played with time scale $k = P\cdot f_0$.
- **Knob range:** $\alpha$ from 13.7 to 18.05. The default is 15.8, with the knob at 0.48, near the middle, so you can turn it both ways. dysts' value, 15.6, is kept only as a reference (the app measures its reference time scale there). The default is the chaotic point nearest the middle of the range (15.875) whose neighbours within 0.1 are chaotic too; the periodic window at 15.95 rules out 15.85 and 15.9. Of the 130 points the app tabulates across the range, about 91% are chaotic.
- **Pitch drift:** $P$ wanders (not monotonically) between 1.409 and 1.685, a band about 3.1 semitones wide. It is about 1.50–1.53 on the single scroll, lowest (about 1.41–1.47) between $\alpha \approx 14.8$ and 15.9, and highest near the top. At the default it is 1.450. At dysts' value it is 1.464; dysts lists 1.4235, about half a semitone shorter. Pitch lock compensates. Without it, the period stays at the default's 1.450, so the note can rise about 0.5 semitone sharp (near $\alpha \approx 14.85$, at the edge of a window) or fall up to about 2.6 semitones flat. That deepest drop occurs only inside the periodic window at $\alpha \approx 17.91$ ($P \approx 1.68$); in the chaotic part of the range the note falls at most about 2.1 semitones flat, near the top.
- **Two characters:** from 13.7 to about 14.43 you hear a single scroll. There are two mirror-image twins, and a box lands on one or the other depending on its history; heard on $y$ they sound the same (one is the other turned upside down). At $\alpha \approx 14.43$ the two scrolls merge and the spread of $x$ roughly doubles. The app evens out the level as the knob moves, so you hear the merge as a change of character, not of loudness.
- **Periodic windows:** the app's table (points 0.034 apart) finds seven inside the range, at $\alpha \approx$ 13.90, 14.82, 15.09, 15.33–15.37, 15.94–15.98, 16.83–16.93 and 17.91. Narrower ones can slip between the points: spot checks every 0.005 also find windows near 14.1 and at 14.69–14.72, and show that the one at 14.82 really spans about 14.80–14.85. In a window the motion repeats exactly, so the buzz clears into a steady harmonic tone. On the double scroll, $y$'s spectral peak sharpens (prominence 0.85–0.93, against about 0.3–0.7 around the windows); on the single scroll, where the peak is already sharp (above 0.9), the change is subtler. If the orbit closes only after several loops (a period-3 window, say), faint undertones below the note can join in. Even the widest window, 16.83–16.93, is only about 2% of the knob's travel, so a sweep passes each window as a brief flash of clean tone; parking the knob inside one holds it. Windows also shift $P$ (by up to about 1 semitone at 17.91), and pitch lock follows.
- **Where the range starts:** below 13.7 there is no chaos at all, down to $\alpha = 8$, the bottom of the explored range. Just below 13.7 is the period-doubling cascade (period 2 from about 13.15, period 4 near 13.6), which turns chaotic only at about 13.7; further down are the simple oscillations born at ≈10.1 and, below that, silence. So the range starts at the first chaotic point. The chaos there is still weak ($\lambda \approx 0.07$: nearby states separate by only about 10% per cycle).
- **Where it stops:** from $\alpha \approx 18.45$ trajectories escape to infinity (in the three-segment model). The app keeps a safety margin of 0.36 in $\alpha$ (3% of the explored width) from any value where that happens, so 18.1 is already too close, and the range stops at the sweep point below it, 18.05.
- **What did not limit it:** turning the knob up or down leads to the same sound (a two-way sweep found no hysteresis); $y$ stays pitched everywhere (prominence at least 0.24, above the 0.15 floor); and $P$ changes smoothly between neighbouring points (at most 5.8%, at the 17.91 window, against the 15% at which pitch lock would glitch).

## Sound notes

To be filled in after listening tests (Phase 1).

Hypotheses (to be tested):

- $y$ should sound clearly pitched. Its spectral-peak prominence is about 0.65 at the default and 0.97 at the bottom (single scroll), but mostly 0.3–0.45 above $\alpha \approx 17$ and 0.24 at the top end, where the chaos is also strongest ($\lambda \approx 0.5$–0.7, against 0.07 at the bottom). So the bottom should be most tonal and the top roughest.
- $x$ (prominence ≈ 0.2 at the default, 0.15 or less above $\alpha \approx 17$) will likely growl: a buzz plus random square-wave-like jumps between scrolls, with strong low-frequency content.
- Crossing $\alpha \approx 14.43$ should sound like a sudden change of character, from a steady buzz to one with random flips.
- A slow sweep should reveal the periodic windows as short moments of clean tone, most clearly at 16.83–16.93.
- Pitch lock may slip by up to about half a semitone right at the edges of some narrow windows: spot checks found 46–48 cents at $\alpha = 14.80$ and 17.90, because those edges are sharper than the table's 0.034 spacing. Listen for a brief detuning there.

## References

1. Chua, L. O. (1992). The genesis of Chua's circuit. *Archiv für Elektronik und Übertragungstechnik (AEÜ)*, 46, 250–257. Preprint: UCB/ERL M92/1. https://www2.eecs.berkeley.edu/Pubs/TechRpts/1992/ERL-92-1.pdf
2. Matsumoto, T. (1984). A chaotic attractor from Chua's circuit. *IEEE Transactions on Circuits and Systems*, 31(12), 1055–1058. https://doi.org/10.1109/TCS.1984.1085459
3. Zhong, G.-Q., & Ayrom, F. (1985). Experimental confirmation of chaos from Chua's circuit. *International Journal of Circuit Theory and Applications*, 13(1), 93–98. https://doi.org/10.1002/cta.4490130109
4. Matsumoto, T., Chua, L. O., & Komuro, M. (1985). The double scroll. *IEEE Transactions on Circuits and Systems*, 32(8), 797–818. https://doi.org/10.1109/TCS.1985.1085791
5. Chua, L. O., Komuro, M., & Matsumoto, T. (1986). The double scroll family. *IEEE Transactions on Circuits and Systems*, 33(11), 1072–1118. https://doi.org/10.1109/TCS.1986.1085869
6. Chua, L. O. (2007). Chua circuit. *Scholarpedia*, 2(10), 1488. https://doi.org/10.4249/scholarpedia.1488
7. Kennedy, M. P. (1991). *Experimental chaos via Chua's circuit*. Memorandum UCB/ERL M91/95, UC Berkeley. https://www2.eecs.berkeley.edu/Pubs/TechRpts/1991/ERL-91-95.pdf
8. Kennedy, M. P. (1993). Three steps to chaos—Part II: A Chua's circuit primer. *IEEE Transactions on Circuits and Systems I*, 40(10), 657–674. https://doi.org/10.1109/81.246141
9. Alligood, K. T., Sauer, T. D., & Yorke, J. A. (1996). *Chaos: An Introduction to Dynamical Systems*. Springer. https://doi.org/10.1007/b97589
10. Rodet, X. (1993). Sound and music from Chua's circuit. *Journal of Circuits, Systems and Computers*, 3(1), 49–61. https://doi.org/10.1142/S0218126693000058 (preprint: UCB/ERL M92/108, https://www2.eecs.berkeley.edu/Pubs/TechRpts/1992/ERL-92-108.pdf)
11. Rodet, X. (1993). Models of musical instruments from Chua's circuit with time delay. *IEEE Transactions on Circuits and Systems II*, 40(10), 696–701. https://doi.org/10.1109/82.246173
12. Mayer-Kress, G., Choi, I., Weber, N., Bargar, R., & Hübler, A. (1993). Musical signals from Chua's circuit. *IEEE Transactions on Circuits and Systems II*, 40(10), 688–695. https://doi.org/10.1109/82.246172
13. Zhong, G.-Q., Bargar, R., & Halle, K. S. (1994). Circuits for voltage tuning the parameters of Chua's circuit: Experimental application for musical signal generation. *Journal of the Franklin Institute*, 331(6), 743–784. https://doi.org/10.1016/0016-0032(94)90088-4
14. Choi, I. (1994). Interactive exploration of a chaotic oscillator for generating musical signals in real-time concert performance. *Journal of the Franklin Institute*, 331(6), 785–818. https://doi.org/10.1016/0016-0032(94)90089-2
15. Bilotta, E., Gervasi, S., & Pantano, P. (2005). Reading complexity in Chua's oscillator through music. Part I: A new way of understanding chaos. *International Journal of Bifurcation and Chaos*, 15(2), 253–382. https://doi.org/10.1142/S0218127405012156
16. Chua, L. O. (1971). Memristor—The missing circuit element. *IEEE Transactions on Circuit Theory*, 18(5), 507–519. https://doi.org/10.1109/TCT.1971.1083337
17. Madan, R. N. (Ed.). (1993). *Chua's Circuit: A Paradigm for Chaos*. World Scientific. https://doi.org/10.1142/1997
18. Gilpin, W. (2021). Chaos as an interpretable benchmark for forecasting and data-driven modelling. *NeurIPS Datasets and Benchmarks Track*. arXiv:2110.05266. Code: https://github.com/GilpinLab/dysts
19. Tucker, W. (1999). The Lorenz attractor exists. *Comptes Rendus de l'Académie des Sciences, Série I, Mathématique*, 328(12), 1197–1202. https://doi.org/10.1016/S0764-4442(99)80439-X
