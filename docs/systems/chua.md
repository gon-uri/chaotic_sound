<!-- Draft written by an AI agent; facts need human review before publishing. Last updated: 2026-10-25 -->

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
- $\alpha = C_2/C_1 = 15.6$ and $\beta = C_2R^2/L = 28$: ratios of component values.
- $h(x)$: Chua's diode, three straight segments with slope $m_0 = -8/7 \approx -1.143$ for $|x|<1$ and $m_1 = -5/7 \approx -0.714$ outside. Both slopes are negative: a "negative resistance".
- The $-x$ term is the ordinary resistor $R$.

**dysts compared with the original.** Chua, Komuro and Matsumoto [5] fold the resistor into the diode, $\dot{x} = \alpha\,(y - \tilde h(x))$, so their slopes are $m_0+1 = -1/7$ and $m_1+1 = 2/7$; their classic double-scroll point is $\alpha = 9$, $\beta = 100/7$. dysts [18] uses another standard point, $\alpha = 15.6$, $\beta = 28$ (Scholarpedia's figures share its $\alpha$, $m_0$, $m_1$ [6]), with the slopes rounded. A real diode has five segments, not three: its outer segments turn passive and keep the voltages bounded [1].

## The parameter you control

The knob sets $\alpha = C_2/C_1$; raising it is like shrinking $C_1$. The sequence at $\beta = 28$ (values below 13.7 come from our own quick simulations and eigenvalue calculations, not yet checked against the literature):

| $\alpha$ | What happens |
|---|---|
| below ≈10.1 | Motion settles on one of the two outer equilibria: silence. |
| ≈10.1 | They lose stability (Hopf-type) and an oscillation is born around each. |
| ≈13.1–13.7 | Period doubling: period 2 from ≈13.15, period 4 near 13.6, then chaos. |
| 13.7–14.4 | Two mirror-image **single-scroll** (Rössler-like) chaotic attractors, with narrow periodic windows (near 13.9 and 14.1). |
| ≈14.4–14.6 | The twins touch and merge into the **double scroll** (attractor-merging crisis). |
| up to ≈18.4 | Double scroll, with narrow periodic windows. |
| ≈18.45 | In the three-segment model, trajectories escape to infinity. |

Kennedy saw the same story on a breadboard, tuning a single component: equilibrium, Hopf, periods 1, 2, 4, a period-3 window, a Rössler-type attractor, the double scroll and finally a large limit cycle on the diode's outer segments [7]. Rodet *heard* the cascade at the classic double-scroll parameters ($\beta = 100/7$, slopes $-1/7$ and $2/7$ in the original form, $\alpha$ from 8.0 to 8.24): harmonic tones whose fundamental halved at each doubling [10].

## Properties

- **Attractor:** two interleaved spirals; Kaplan–Yorke dimension ≈ 2.11 (dysts).
- **Equilibria:** the origin and $P^\pm = (\pm 1.5, 0, \mp 1.5)$, all unstable at the default, as Chua designed [1]. $P^\pm$ are saddle-foci (eigenvalues $\approx 0.31 \pm 4.52i$, $-6.07$): trajectories spiral outward until thrown across the middle.
- **Piecewise linear:** in each slab ($x<-1$, $|x|<1$, $x>1$) the equations are linear and exactly solvable, which made a proof possible [5, 6].
- **Symmetry:** $(x,y,z)\mapsto(-x,-y,-z)$.
- **Dissipation:** the divergence is $\alpha/7 - 1 \approx +1.23$ in the middle slab (volumes grow) and $-2\alpha/7 - 1 \approx -5.46$ outside; on average volumes shrink (dysts' exponents sum to ≈ −3.86).
- **Lyapunov exponents:** we measure $\lambda \approx 0.455$ at the default. dysts' spectrum, $(0.46, 0.00, -4.32)$, agrees; its separate largest-exponent estimate, 1.23, is higher. Since $\lambda P \approx 0.67$, nearby states drift apart about twofold per cycle.
- **Phase coherence:** partial. The spin around each scroll is fairly regular, with a period of about 1.4–1.7 time units across the knob's range (1.46 at the default). The linear estimate at $P^\pm$, $2\pi/4.52 \approx 1.39$, slightly underestimates it, and the cycle-to-cycle spread grows toward the top of the range. The hops between scrolls are irregular. $y$ is centred on 0 at every equilibrium, so hops barely disturb it, while $x$ jumps between about ±1.5.
- **Boundedness:** the three-segment model is not globally bounded; a physical circuit is.

## History

**One evening in Tokyo.** Leon O. Chua (born 1936 in the Philippines, at UC Berkeley since 1971, also known for predicting the memristor [16]) arrived in Tokyo in late October 1983 for a fellowship. The next day he visited Takashi Matsumoto's lab at Waseda University to see what was meant to be the first electronic circuit obeying the Lorenz equations. After more than a year of work, it failed: the analog multipliers it needed were not good enough [1].

That night Chua reasoned that the Lorenz and Rössler systems both owe their chaos to at least two unstable equilibria. In under an hour he listed eight candidate circuits and narrowed them to one, scribbling on napkins and envelopes because his new dormitory had no paper. Next morning Matsumoto programmed it (in BASIC) and soon found a strange attractor [1]. He published it in December 1984 and named it "Chua's circuit" [2].

**Seen, built, proven.** Matsumoto's group had held off building the circuit, so Chua asked G.-Q. Zhong and F. Ayrom in Berkeley. Their breadboard worked with almost no tuning [1, 3]. The 1985 paper "The double scroll" described the attractor in detail [4]. In 1986 Chua, Komuro and Matsumoto exploited the piecewise-linear structure to prove that, for some parameter values, the circuit has chaotic dynamics in the sense of Shil'nikov's theorem [5]. Chaos had now been seen in simulation, in the lab and in a proof; in 1993 Kennedy called it the only physical system with mathematically proven chaos [8]. The Lorenz attractor waited until 1999 [6].

**Influence.** Kennedy's version uses two op-amps and off-the-shelf parts [7]; textbooks adopted it [9]; a 1993 book called it "a paradigm for chaos" [17].

**Sound and music.** In the early 1990s at Berkeley's CNMAT, Xavier Rodet (IRCAM) simulated it in real time and listened: periodic regimes gave harmonic tones, chaos gave noise mixed with harmonics. A time-delayed version modelled clarinet-like instruments [10, 11]. He notes that David Wessel used its output to drive pitch, duration and dynamics [10]. Mayer-Kress and colleagues [12], Zhong, Bargar and Halle (voltage-controlled tuning for live use) [13], Choi (real-time concert performance) [14] and Bilotta and colleagues [15] followed.

## In chaotic_sound

Numbers are in the system's own time units.

- **What you hear:** by default $y$, the most pitched variable. The app measures the period $P$ of $y$'s strongest spectral peak and plays your note with time scale $k = P\cdot f_0$.
- **Knob range:** $\alpha$ from 13.7 to 18.05; the default 15.6 sits a little below the middle. About 91% of 33 tested points are chaotic.
- **Pitch drift:** $P$ wanders (not monotonically) between about 1.41 and 1.69, a band about 3 semitones wide. At the default it is 1.464; dysts lists 1.4235, about half a semitone shorter. Pitch lock compensates; without it the note can fall up to about 2.4 semitones flat (or rise about 0.6 semitone sharp).
- **Two characters:** from 13.7 to about 14.4 you hear a single scroll. Near 14.4–14.6 the scrolls merge and the spread of $x$ doubles.
- **Periodic windows:** the project's sweep flags narrow windows at $\alpha \approx$ 14.1, 14.7, 14.8–14.85, 15.35, 15.95 and 16.85–16.9. The list is not complete: finer checks also find windows near 13.9, 15.1 and 17.9. Crossing one, the sound briefly locks into a clean harmonic tone.
- **The ends:** below the bottom, at $\alpha \approx 13.3$, the motion is periodic (in our simulations, the period-2 stage of the cascade), so the range starts just above it. From $\alpha \approx 18.45$ trajectories escape to infinity; 18.05 keeps a safety margin.

## Sound notes

To be filled in after listening tests (Phase 1).

Hypotheses (to be tested):

- $y$ should sound clearly pitched: its peak prominence is about 0.5 at the default and near 1 at the bottom (single scroll), so the bottom should be most tonal and the top roughest.
- $x$ (prominence ≈ 0.2) will likely growl: a buzz plus random square-wave-like jumps between scrolls, with strong low-frequency content.
- Crossing $\alpha \approx 14.4$–14.6 should sound like a sudden change of character, from a steady buzz to one with random flips.

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
