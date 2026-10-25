<!-- Draft written by an AI agent; facts need human review before publishing. Last updated: 2026-10-25 -->

# Lorenz system

> Three short equations for a heated fluid that never repeats itself: the system most often linked to the "butterfly effect".

## In plain words

Picture a pan of water heated from below. Warm water rises, cool water sinks, and the fluid turns over in slow rolls. In 1963 the meteorologist Edward Lorenz boiled this picture down to three numbers: how fast the roll turns, how much warmer the rising side is than the sinking side, and how far the temperature from bottom to top departs from a straight line. With enough heating the roll never settles: it turns one way for a while, flips, turns the other way, and no two stretches are ever the same.

Plotted in 3D, the motion traces two looping "wings". The path circles one wing a few times, crosses to the other, and keeps going. Nothing in it is random, yet two starts that differ by a hair soon go completely different ways. Think of a player who keeps circling a short riff and then, without warning, switches to its mirror image: the loops give a pulse, the switches can't be predicted.

## Equations

$$
\begin{aligned}
\dot{x} &= \sigma\,(y - x)\\
\dot{y} &= x\,(\rho - z) - y\\
\dot{z} &= x\,y - \beta\,z
\end{aligned}
$$

- $x$ is proportional to the strength of the convective roll; its sign gives the direction of turning.
- $y$ is proportional to the temperature difference between rising and sinking fluid.
- $z$ is proportional to how far the vertical temperature profile departs from a straight line.
- $\sigma = 10$: the Prandtl number (viscosity over heat diffusivity).
- $\rho = 28$: the Rayleigh number over its value at the onset of convection, i.e. how hard the layer is heated.
- $\beta = 2.667$: a geometric factor set by the width-to-height ratio of the rolls.

**dysts vs. the original.** The form is exactly that of Lorenz (1963) [1], who wrote $X, Y, Z$ and $\sigma, r, b$. dysts [18] uses $\beta = 2.667$ instead of $8/3 \approx 2.6667$, which shifts the landmarks below only slightly (the Hopf value moves from 24.737 to 24.739). Keeping only three Fourier modes is a drastic simplification: the model is the classic paradigm of chaos, but far above onset it is not a faithful picture of real convection (unverified).

## The parameter you control

$\rho$ is the heating knob. Classical landmarks for $\sigma = 10$, $\beta = 8/3$ [3, 7, 13]:

| $\rho$ | What happens |
|---|---|
| $< 1$ | The fluid stays still: every trajectory goes to the origin. |
| $1$ | Convection starts (pitchfork bifurcation): two steady rolls $C^\pm$ appear and are stable. |
| $\approx 13.93$ | A "homoclinic explosion" creates a non-attracting chaotic set: trajectories wander chaotically, then settle onto a steady roll (transient chaos). |
| $\approx 24.06$ | A chaotic attractor appears, coexisting with the still-stable steady rolls. |
| $\approx 24.74$ | $\rho_H = \sigma(\sigma+\beta+3)/(\sigma-\beta-1)$: the rolls lose stability in a subcritical Hopf bifurcation; chaos is the only attractor left. |
| $24.8$–$71.26$ | The range of the chaotic_sound knob; Lorenz's classical value 28 sits near its bottom. |
| $69.72$–$69.84$, $71.41$–$71.52$ | Two of many thin periodic windows (stable orbits of period 8 and 4 in symbolic terms) [13]. |
| $\approx 99.5$–$100.8$, $\approx 146$–$166$ | Wider periodic windows, with period-doubling cascades at their lower edges [3, 13]. |
| above $\approx 229$ | Published tables list a stable periodic orbit throughout, up to $\rho = 10\,000$ [13]. |

Above 24.74 chaos is the rule, but many periodic windows, most extremely thin, are scattered through it [13]. Turning $\rho$ up also makes the attractor bigger (the wing centres sit at $z = \rho - 1$) and the loops faster.

## Properties

- **Attractor:** a two-lobed strange attractor; Kaplan–Yorke dimension ≈ 2.06 (Sprott [10]; dysts lists 2.08), correlation dimension ≈ 2.05 [11]. Smale's 14th problem [9] asked whether the equations really behave like the idealized "geometric Lorenz attractor", and so have a genuine strange attractor. Warwick Tucker's 2002 computer-assisted proof (for the classical $\beta = 8/3$) answered yes and showed that the attractor survives small changes to the equations [8].
- **Equilibria:** the origin (a saddle) and $C^\pm = (\pm\sqrt{\beta(\rho-1)},\ \pm\sqrt{\beta(\rho-1)},\ \rho-1)$, at $\rho = 28$ unstable saddle-foci spinning at ≈ 10.2 rad per time unit.
- **Symmetry:** $(x,y,z)\mapsto(-x,-y,z)$; the attractor as a whole is symmetric.
- **Dissipation:** constant divergence $-(\sigma+1+\beta) \approx -13.67$: volumes shrink about a millionfold per time unit, so transients die fast.
- **Lyapunov exponents:** $(0.906,\ 0,\ -14.57)$ (Sprott [10]); dysts estimates $(1.09,\ 0.03,\ -14.9)$ and, separately, $\lambda_{\max} \approx 0.892$.
- **Phase coherence:** mixed, which matters for pitch. Random wing switching smears the spectra of $x$ and $y$; $z$ rises and falls once per loop on either wing, so its peak is much sharper. Pikovsky and co-workers contrasted Lorenz with the more coherent Rössler system and defined a phase from the projection $(\sqrt{x^2+y^2},\, z)$ [12].
- **Boundedness:** all trajectories enter a bounded ellipsoid [1], so integration is safe. On the attractor $z$ stays positive (mean ≈ 23.5 at $\rho = 28$).

## History

Edward Norton Lorenz (1917–2008) was a meteorologist at MIT. Around 1960–61 he ran a 12-variable weather model on a Royal McBee LGP-30, a desk-sized vacuum-tube computer. One day he restarted a run from a printout that showed three decimals while the machine kept six (in Gleick's telling, 0.506 instead of 0.506127 [19]). After about two simulated months the new run bore no resemblance to the old one [6]. The episode is usually dated to 1961, though Lorenz had mentioned the effect at a conference in Tokyo in November 1960 [6].

Seeking the simplest system with this behaviour, Lorenz turned to a seven-mode convection model by his colleague Barry Saltzman [2]; in one non-settling solution only three variables stayed active, and Lorenz kept those [1]. *Deterministic Nonperiodic Flow* (1963) [1] showed sensitivity to tiny changes in the starting point, motion on a thin, infinitely layered set, and a simple one-dimensional map linking successive maxima of $z$. Its conclusion: forecasting the sufficiently distant future is impossible in practice. The paper thanks Ellen Fetter for the numerical computations; before her, Margaret Hamilton, later head of Apollo's on-board flight software, had programmed the LGP-30 for Lorenz [6].

Recognition was slow: outside meteorology the paper was cited only three times in its first decade [14]. In a 1963 paper Lorenz quoted an unnamed meteorologist: if the theory were right, one flap of a sea gull's wings could change the weather forever [4]. The butterfly arrived on 29 December 1972, at the AAAS meeting in Washington, D.C., when convener Philip Merilees titled Lorenz's talk *Predictability: Does the Flap of a Butterfly's Wings in Brazil Set Off a Tornado in Texas?* [5]. That talk drew on Lorenz's 1969 study of flows with many scales of motion [20] rather than on the three-variable model, a distinction the popular story usually skips [21].

"Chaos" entered mathematics with Li and Yorke (1975) [15]; the same year Haken showed that a single-mode laser obeys Lorenz-equivalent equations [16]. In music, Diana Dabby used pairs of nearby Lorenz trajectories to generate variations of existing pieces [17].

## In chaotic_sound

The knob sweeps $\rho$ from 24.8 to 71.26; the default, Lorenz's 28, sits about 7% of the way up. All times are in the system's own units.

- **Which variable sets the pitch.** The tuning observable is $z$. Its loop gives a clear spectral peak (prominence ≈ 0.4 across the range, against ≈ 0.03 for $x$ and $y$, which are dominated by slow wing switching). At the default that peak has period $P = 0.7522$. To play a note $f_0$, the app runs the equations $k = P \cdot f_0$ times faster than system time: for A4 = 440 Hz, about 331 time units per second. dysts lists a period of 1.50, almost exactly twice ours (an octave lower); we tune to the faster loop of $z$ because it carries the clearest peak.
- **How the period moves.** $P$ shrinks steadily from 0.826 at the bottom to 0.439 at the top: a factor of 1.9, about 11 semitones. With pitch lock on, the app follows this table, so the note stays put and only the timbre changes; with it off, the pitch drifts from about 1.6 semitones below the default to 9.3 above.
- **How chaotic it is.** We measured $\lambda = 0.891$ at the default, in line with dysts (0.892) and Sprott (0.906, for $\beta = 8/3$). Nearby trajectories separate by a factor $e$ every 1.1 time units, about 1.5 loops ($\lambda P \approx 0.67$ per loop). Towards the top $\lambda$ grows to roughly 1.4–1.5 per time unit, but the loops shorten at nearly the same rate, so the divergence per loop stays near 0.6–0.7 across the whole range.
- **Periodic windows.** 32 of 33 sample points are chaotic. The exception, $\rho \approx 69.8$, falls in the published period-8 window at 69.72–69.84 [13]. The pitch-lock table replaces that point's odd period with its neighbour's, so the note does not jump, but a knob resting in that sliver should give an exactly repeating pattern. Further published windows lie between about 48 and 66 (e.g. 50.30–50.32, 58.700–58.715, 64.895–64.898) [13]; that list is not exhaustive and starts only at $\rho = 28$. Like the 69.8 window, they are far narrower than the grid spacing (≈ 1.45), so the sampling missed them.
- **Why the range ends where it does.** The bottom, 24.8, is just above $\rho_H \approx 24.74$, so a modulated box can never fall onto a steady roll (a silent fixed point). The top, 71.26, is just below $\rho \approx 71.49$, where a finer sweep saw the period jump by 32%. That value lies inside the published period-4 window at 71.41–71.52 [13], which would explain the jump.

## Sound notes

To be filled in after listening tests (Phase 1).

Hypotheses, to be tested:

- *Hypothesis:* $z$ should sound clearly pitched but slightly unsteady, while $x$ and $y$ (prominence ≈ 0.03) should sound like a rumbling, barely pitched texture whose polarity flips at random moments.
- *Hypothesis:* with pitch lock on, turning $\rho$ up should change the timbre more than the roughness, since the divergence per cycle stays near 0.6–0.7 throughout. With it off, bottom to top raises the pitch about 11 semitones and the divergence per second about 1.8×.
- *Hypothesis:* inside the window near $\rho \approx 69.8$ the sound should snap to a steady tone, possibly with subharmonics, since the pattern repeats only every few loops.

## References

1. Lorenz, E. N. (1963). Deterministic nonperiodic flow. *Journal of the Atmospheric Sciences*, 20(2), 130–141. https://doi.org/10.1175/1520-0469(1963)020<0130:DNF>2.0.CO;2
2. Saltzman, B. (1962). Finite amplitude free convection as an initial value problem—I. *Journal of the Atmospheric Sciences*, 19(4), 329–341. https://doi.org/10.1175/1520-0469(1962)019<0329:FAFCAA>2.0.CO;2
3. Sparrow, C. (1982). *The Lorenz Equations: Bifurcations, Chaos, and Strange Attractors*. Applied Mathematical Sciences 41. Springer. https://doi.org/10.1007/978-1-4612-5767-7
4. Lorenz, E. N. (1963). The predictability of hydrodynamic flow. *Transactions of the New York Academy of Sciences*, 25(4), 409–432. https://doi.org/10.1111/j.2164-0947.1963.tb01464.x
5. Lorenz, E. N. (1993). *The Essence of Chaos*. University of Washington Press. (Appendix 1 reprints the 1972 AAAS talk.)
6. Sokol, J. (2019, May 20). The hidden heroines of chaos. *Quanta Magazine*. https://www.quantamagazine.org/hidden-heroines-of-chaos-ellen-fetter-and-margaret-hamilton-20190520/
7. Strogatz, S. H. (2024). *Nonlinear Dynamics and Chaos* (3rd ed.), ch. 9. Chapman and Hall/CRC. https://doi.org/10.1201/9780429398490
8. Tucker, W. (2002). A rigorous ODE solver and Smale's 14th problem. *Foundations of Computational Mathematics*, 2(1), 53–117. https://doi.org/10.1007/s002080010018
9. Smale, S. (1998). Mathematical problems for the next century. *The Mathematical Intelligencer*, 20(2), 7–15. https://doi.org/10.1007/BF03025291
10. Sprott, J. C. Lyapunov exponent spectrum software (values for the Lorenz attractor). https://sprott.physics.wisc.edu/chaos/lespec.htm
11. Grassberger, P., & Procaccia, I. (1983). Measuring the strangeness of strange attractors. *Physica D*, 9(1–2), 189–208. https://doi.org/10.1016/0167-2789(83)90298-1
12. Pikovsky, A., Rosenblum, M., Osipov, G., & Kurths, J. (1997). Phase synchronization of chaotic oscillators by external driving. *Physica D*, 104(3–4), 219–238. https://doi.org/10.1016/S0167-2789(96)00301-6
13. Hao, B.-L., Liu, J.-X., & Zheng, W.-M. (1998). Symbolic dynamics analysis of the Lorenz equations. *Physical Review E*, 57(5), 5378–5396. https://doi.org/10.1103/PhysRevE.57.5378 (arXiv:chao-dyn/9710014)
14. Siegfried, T. (2013, September 16). Born half a century ago, chaos theory languished for years. *Science News*. https://www.sciencenews.org/article/born-half-century-ago-chaos-theory-languished-years
15. Li, T.-Y., & Yorke, J. A. (1975). Period three implies chaos. *The American Mathematical Monthly*, 82(10), 985–992. https://doi.org/10.1080/00029890.1975.11994008
16. Haken, H. (1975). Analogy between higher instabilities in fluids and lasers. *Physics Letters A*, 53(1), 77–78. https://doi.org/10.1016/0375-9601(75)90353-9
17. Dabby, D. S. (1996). Musical variations from a chaotic mapping. *Chaos*, 6(2), 95–107. https://doi.org/10.1063/1.166171
18. Gilpin, W. (2021). Chaos as an interpretable benchmark for forecasting and data-driven modelling. *NeurIPS Datasets and Benchmarks Track*. arXiv:2110.05266. Code: https://github.com/GilpinLab/dysts
19. Gleick, J. (1987). *Chaos: Making a New Science*. Viking.
20. Lorenz, E. N. (1969). The predictability of a flow which possesses many scales of motion. *Tellus*, 21(3), 289–307. https://doi.org/10.3402/tellusa.v21i3.10086
21. Palmer, T. (2024). The real butterfly effect and maggoty apples. *Physics Today*, 77(5), 30–35. https://doi.org/10.1063/pt.eike.hsbz
