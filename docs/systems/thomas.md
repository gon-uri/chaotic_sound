<!-- Draft written by an AI agent; facts need human review before publishing. Last updated: 2026-10-25 -->

# Thomas' cyclically symmetric attractor

> Three identical equations, each variable nudged by the next one around a loop: a particle lost in an endless three-dimensional labyrinth.

## In plain words

Imagine a small ball drifting through an endless 3D maze whose walls are gentle hills and valleys, repeating in every direction like egg boxes stacked in three dimensions. The slopes keep pushing the ball and friction keeps slowing it. With the right amount of friction it never settles: it rattles from cell to cell along a path that never repeats.

The Belgian biologist René Thomas wrote this down as three equations that are copies of one another: x is pushed by y, y by z, and z by x, closing a loop. Rotate the names around the loop and nothing changes; that is the "cyclic symmetry". Think of a three-voice round in which each voice reacts only to the next. With a lot of friction the ball comes to rest or circles a regular loop. With less, it ranges further and its path becomes chaotic. With none at all it wanders the whole labyrinth like a drunkard's walk, although nothing in it is random.

## Equations

The project uses the dysts form [11]:

$$
\begin{aligned}
\dot{x} &= -a\,x + b\,\sin y\\
\dot{y} &= -a\,y + b\,\sin z\\
\dot{z} &= -a\,z + b\,\sin x
\end{aligned}
$$

- $x, y, z$ locate a point, pictured as a particle moving through a lattice of forces [11].
- $b\sin(\cdot)$ is the push each variable gets from the next one around the loop. Because the sine changes sign every $\pi$, the pushes form a repeating lattice.
- $a$ is the damping (friction): on its own, each variable would relax back towards 0 at rate $a$.
- Project defaults: $a = 1.85$, $b = 10$.

**dysts compared with the original.** Thomas [1] and Sprott & Chlouverakis [2] write

$$
\dot{x} = \sin y - \beta x,\qquad \dot{y} = \sin z - \beta y,\qquad \dot{z} = \sin x - \beta z .
$$

The literature calls the damping $b$, which clashes with dysts' forcing strength, so this page writes $\beta$. Rescaling time, $t_\text{classical} = b\,t_\text{dysts}$, turns the dysts form into the classical one with $\beta = a/b$. The defaults thus mean $\beta = 0.185$, and one dysts time unit equals 10 classical ones. With $b = 10$ fixed, the knob changes only $\beta$.

## The parameter you control

The knob moves the damping $a$, that is, the friction $\beta = a/10$. Here is what happens as the friction is lowered:

| $\beta$ ($a = 10\beta$) | What happens |
|---|---|
| $> 1$ | Everything settles at the origin. |
| $1$ | Pitchfork bifurcation: the origin becomes unstable and two stable equilibria appear on the diagonal $x = y = z$ [2]. |
| $\approx 0.329$ | Hopf bifurcation: both equilibria lose stability at once, and each gives birth to a steady oscillation (a mirror-image pair) [2]. |
| $0.329$–$0.208$ | The cycles grow and period-double, in a sequence more intricate than a plain cascade, with period-three-like windows [8]. Several cycles can coexist: four at 0.220, six at 0.204 [2]. |
| $\approx 0.208$ | A band of chaos sets in [2]. |
| $0.203$, $0.2$ | Coexisting strange attractors: six at 0.203 [2], two at 0.2 [4]. Slightly past the onset of chaos such attractors generally merge into one [2]. |
| $0.19$ | An intricate but stable periodic orbit [4]. |
| $0.18$ | A single chaotic attractor [4]. Sprott & Chlouverakis place an interior crisis near this value, after which a new stable cycle appears; they find three coexisting cycles at 0.173 [2]. |
| $0.18$–$0.11$ | More crises, cycles and chaotic bands. Below about 0.11 chaos dominates and the dimension rises smoothly towards 3 [2]. |
| $0$ | No friction. The flow conserves volume, its equilibria form an infinite lattice at $(l\pi, m\pi, n\pi)$, and trajectories wander through it in a "chaotic walk" [3]. This is the limiting case of what Thomas called *labyrinth chaos*, a term that also covers the damped attractors weaving among many unstable equilibria [1, 2]. |

At $\beta = 0$ the walk spreads slightly faster than ordinary diffusion (Hurst exponent ≈ 0.61) [2]. The app's knob covers $\beta \approx 0.178$–$0.195$, the busiest part of the table, which is why the usable band is narrow and full of windows.

## Properties

- **Attractor:** a single strange attractor at the default. It weaves among 27 unstable equilibria, a 3×3×3 block of Thomas's lattice: the origin, a pair on the diagonal at $x = y = z \approx \pm 2.63$, and 24 others (our numerical count).
- **Dimension:** our $\lambda$ gives a Kaplan–Yorke dimension of about 2.08 (exponents $\lambda$, 0, $-3a-\lambda$); dysts lists 2.13. Sprott & Chlouverakis find about 2.16 at $\beta = 0.1$ [2].
- **Symmetries:** cyclic, $(x,y,z)\mapsto(y,z,x)$, and inversion, $(x,y,z)\mapsto(-x,-y,-z)$. An attractor lacking part of this symmetry must coexist with its copies, one source of multistability.
- **Dissipation:** the divergence is constant, $-3a = -5.55$ per dysts time unit. Phase-space volume shrinks by a factor of about $2\times10^{-4}$ per oscillation, and the dissipation vanishes as $\beta \to 0$.
- **Phase coherence:** low. At the default, the spectrum of $x$ has a peak prominence of only about 0.1–0.25 and no sharp line. The trajectory hops between neighbouring cells instead of circling one centre.
- **Lyapunov exponents:** we measure $\lambda_{\max} \approx 0.494$ per dysts time unit (0.049 per classical unit). dysts lists a maximum exponent of 0.632, about 28% above ours, and a separate spectrum estimate $(0.76, 0.06, -6.42)$ whose leading entry is higher still; since the middle exponent of such a flow is exactly 0, these figures are rough. Per oscillation $\lambda P \approx 0.76$: nearby trajectories roughly double their separation every cycle.
- **Boundedness:** because $\dot{x} = \sin y - \beta x$, $|x|$ cannot stay above $1/\beta$. Every trajectory ends up inside the cube $|x|,|y|,|z| \le 1/\beta \approx 5.4$, so integration is safe.

## History

**A geneticist's rules.** René Thomas (1928–2017) worked mostly at the Université libre de Bruxelles. After a 1952 thesis on DNA under Jean Brachet and a stay with Alfred Hershey at Cold Spring Harbor, he studied bacteriophage λ. The intricate switch by which the virus either kills its host or lies dormant led him to model gene networks with Boolean "kinetic logic" [9]. From such networks he drew two rules (1981) [5]: a positive feedback circuit is needed for several stable states (cell memory, differentiation), and a negative circuit is needed for sustained oscillation. The first rule was later proved as a general theorem by Soulé (2003) [6]; versions of the second have been proved only under extra assumptions [12]. *Biological Feedback* (1990, with Richard D'Ari) set out the approach [7].

**From circuits to chaos.** Thomas then asked what circuits chaos requires, and suggested it needs both a positive and a negative one [4]. In his 1999 paper he revisited Rössler's chaotic equations in terms of feedback circuits and constructed labyrinth chaos [1]. The key is the sine: the single loop $x \leftarrow y \leftarrow z \leftarrow x$ is positive in some regions of space and negative in others, so one loop can supply both ingredients [4]. Without damping, it yields an infinite lattice of unstable steady states [1].

With Otto Rössler, Vasileios Basios and others, Thomas extended the idea to more variables, obtaining hyperchaos of any order and chaotic walks (2004) [3]. In their detailed 2007 study, Sprott and Chlouverakis credit Thomas with bringing the system to their attention [2].

**Music.** Basios and Antonopoulos remember him as an amateur astronomer, full of stories from past climbing expeditions, who never stopped talking about music; his favourite composer was Haydn [4]. He also played the oboe as an amateur and later studied the theory of musical temperaments [9]. Fittingly, Haydn's oratorio *The Creation* opens with an orchestral "Representation of Chaos" [13]. The system has since reached electronic music, for example as a "Thomas Attractor" modulation-source module for Cherry Audio's Voltage Modular [10].

## In chaotic_sound

Numbers below are in dysts time units.

- **Range.** The knob sweeps $a$ from 1.783 to 1.945 ($\beta \approx 0.178$–$0.195$); the default 1.85 sits at about 41% of the travel.
- **Tuning.** The note comes from $x$. With no sharp spectral peak to lock onto, the period is the mean time between successive maxima of $x$ above its average: $P \approx 1.545$ at the default, about 15.5 classical units. Time is rescaled by $k = P f_0$, so for A4 (440 Hz) the system runs about 680 time units per second of sound. dysts lists a period of 4.97, about three times longer; with no clear peak, different methods can disagree widely.
- **Period across the range.** In the app's table $P$ varies between 1.389 and 1.700, not monotonically: about 22%, or three and a half semitones. With pitch lock on, the app follows $P(a)$ and the note stays put. With it off, sweeping the knob bends the pitch by up to about 1.8 semitones up or 1.7 down.
- **Periodic windows.** About 73% of the 130 points in the app's table are chaotic ($\lambda P > 0.05$; a coarser 33-point sweep gave 70%). Narrow windows sit near $a \approx$ 1.792, 1.825, 1.858 and 1.89–1.90, and at the very top (1.941–1.945), plus about ten shorter ones in the table; more may hide between points. The widest, 1.886–1.902, contains $\beta = 0.19$, where a stable periodic orbit has been reported [4]. In a window the noise collapses into a steady periodic waveform with a fixed timbre.
- **Why the range ends where it does.**
  - Below $a \approx 1.72$ ($\beta \approx 0.172$), following the attractor down from the default leads onto a wide periodic branch, so the range starts a little above it. This may be the stable cycle that Sprott & Chlouverakis find after their crisis near $\beta \approx 0.18$ [2] (our interpretation).
  - At the top, the coarse sweep stopped at $a \approx 1.967$, below a jump in the measured period near 1.975 that would make pitch lock glitch; the finer table pass then found non-stationary motion at $a \approx 1.947$ and trimmed the range to 1.945. In our simulations at 1.947–1.975, trajectories stay centred for a while, then drop onto one of a mirror-image pair of attractors confined to one side of the origin (mean about ±1.85 in every variable). That switch explains the drift and plausibly the jump.

## Sound notes

To be filled in after listening tests (Phase 1).

Hypotheses (to be tested):

- With a peak prominence of only about 0.1–0.25, $x$ should sound like pitched noise, breathy and rough, with the note heard as a coloured band rather than a clear tone. It should be the least pitched of the project's five systems.
- A slow knob sweep should flicker between noise and short buzzy tones as it crosses windows, where the prominence jumps to about 0.8. Because attractors coexist, the result may depend on the direction of the sweep (hysteresis).
- By symmetry, $x$, $y$ and $z$ should sound alike, so sending two of them to the left and right channels may give a wide but coherent stereo image.

## References

1. Thomas, R. (1999). Deterministic chaos seen in terms of feedback circuits: analysis, synthesis, "labyrinth chaos". *International Journal of Bifurcation and Chaos*, 9(10), 1889–1905. https://doi.org/10.1142/S0218127499001383
2. Sprott, J. C., & Chlouverakis, K. E. (2007). Labyrinth chaos. *International Journal of Bifurcation and Chaos*, 17(6), 2097–2108. https://doi.org/10.1142/S0218127407018245 (author's copy: https://sprott.physics.wisc.edu/pubs/paper302.htm)
3. Thomas, R., Basios, V., Eiswirth, M., Kruel, T., & Rössler, O. E. (2004). Hyperchaos of arbitrary order generated by a single feedback circuit, and the emergence of chaotic walks. *Chaos*, 14(3), 669–674. https://doi.org/10.1063/1.1772551
4. Basios, V., & Antonopoulos, C. G. (2019). Hyperchaos & labyrinth chaos: revisiting Thomas–Rössler systems. *Journal of Theoretical Biology*, 460, 153–159. https://doi.org/10.1016/j.jtbi.2018.10.025 (preprint: arXiv:1810.06137)
5. Thomas, R. (1981). On the relation between the logical structure of systems and their ability to generate multiple steady states or sustained oscillations. In *Numerical Methods in the Study of Critical Phenomena*, Springer Series in Synergetics 9, 180–193. https://doi.org/10.1007/978-3-642-81703-8_24
6. Soulé, C. (2003). Graphic requirements for multistationarity. *ComPlexUs*, 1(3), 123–133. https://doi.org/10.1159/000076100
7. Thomas, R., & D'Ari, R. (1990). *Biological Feedback*. CRC Press.
8. McDonald, B., & Roy Choudhury, S. (2020). The Thomas attractor with and without delay: complex dynamics to amplitude death. *Discontinuity, Nonlinearity, and Complexity*, 9(1), 27–45. https://doi.org/10.5890/DNC.2020.03.003
9. "René Thomas (biologist)". *Wikipedia*. https://en.wikipedia.org/wiki/Ren%C3%A9_Thomas_(biologist) (accessed 2026-10-25). See also "Thomas' cyclically symmetric attractor", https://en.wikipedia.org/wiki/Thomas%27_cyclically_symmetric_attractor
10. Benard. *Thomas Attractor* (module for Voltage Modular). Cherry Audio store. https://store.cherryaudio.com/modules/thomas-attractor (accessed 2026-10-25)
11. Gilpin, W. (2021). Chaos as an interpretable benchmark for forecasting and data-driven modelling. *NeurIPS Datasets and Benchmarks Track*. arXiv:2110.05266. Code: https://github.com/GilpinLab/dysts
12. Snoussi, E. H. (1998). Necessary conditions for multistationarity and stable periodicity. *Journal of Biological Systems*, 6(1), 3–9. https://doi.org/10.1142/S0218339098000042
13. "The Creation (Haydn)". *Wikipedia*. https://en.wikipedia.org/wiki/The_Creation_(Haydn) (accessed 2026-10-25)
