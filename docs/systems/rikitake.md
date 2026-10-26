<!-- Draft written by an AI agent; facts need human review before publishing. Last updated: 2026-10-26 -->

# Rikitake dynamo

> Two spinning copper discs, each powering the other's magnet: a tabletop cartoon of the Earth's core, in which the magnetic field flips without warning.

## In plain words

Spin a copper disc near a magnet and a current flows between its axle and its rim, as Michael Faraday showed in 1831. Feed that current through a coil that makes the very field the disc spins in, and the machine sustains its own field: a self-exciting dynamo. Earth makes its field in a related way, with molten iron flowing in its outer core. Yet rocks show that Earth's poles have swapped many times, at irregular moments, which a single disc never does [2, 3].

In 1958 Tsuneji Rikitake took two identical discs, drove both with the same steady push, and crossed the wiring: each disc spins in the field of the *other* disc's coil [15]. The currents swing with growing amplitude around one polarity until, suddenly, both change sign and the swinging resumes around the other. When the next flip will come cannot be predicted in practice.

For a musician: the disc speed $z$ rises and falls once per swing, a steady pulse, while the currents $x$ and $y$ carry the flips, like a bass line that jumps to its mirror image at random.

## Equations

$$
\begin{aligned}
\dot{x} &= -\mu\,x + y\,z\\
\dot{y} &= -\mu\,y - a\,x + x\,z\\
\dot{z} &= 1 - x\,y
\end{aligned}
$$

- $x$, $y$: the currents in the two circuits. Disc 1 spins in coil 2's field, so the voltage driving $x$ is proportional to $y\,z$.
- $z$: the angular velocity of disc 1. Disc 2 turns at $z - a$, hence the $(z - a)\,x$ in $\dot y$.
- In $\dot z$, the 1 is the constant driving torque and $-xy$ the magnetic braking.
- $a = 1$: the difference between the two disc speeds.
- $\mu = 1$: resistive damping, proportional to each circuit's electrical resistance [15].

**dysts compared with the original.** Rikitake wrote four equations, one per current and one per disc speed [1, 5]. Both speeds obey the same equation, so their difference $a$ never changes, which leaves three: the system analysed by Cook and Roberts [4] and used by dysts (class `RikitakeDynamo`) [14] (whether Cook and Roberts used exactly these symbols is unverified). dysts takes $a = \mu = 1$. All quantities are dimensionless.

## The parameter you control

$\mu$ sets how fast current drains away as heat. With $a = 1$ (rows after the first are our own sweeps and runs; we found no published map):

| $\mu$ | What happens |
|---|---|
| 0 | No resistance: the flow preserves volume (divergence $-2\mu$), so nothing can attract, and there are no equilibria. |
| 0.2–0.5 | Periodic in our runs ($\lambda \approx 0$; $x$ flips sign on every swing). |
| ≈ 0.51 | Chaos sets in; the knob starts at 0.513. Here the field flips on every swing; up to $\mu \approx 0.6$, usually every one or two swings. |
| 0.54–0.76 | At least eight narrow periodic windows: 0.54–0.56, 0.574, 0.606, 0.630, 0.642, 0.666, 0.706 and 0.75. The catalog's 130-point table resolves only the first two. A scan at steps of 0.002 found no window from 0.76 to 1.8. |
| ≈ 0.7–0.8 | Strongest chaos, $\lambda \approx 0.14$–$0.15$ per time unit, on a broad plateau. |
| 1 | The dysts value. The equilibria sit at $z = (1+\sqrt5)/2$, the golden ratio. |
| 1.153 | The chaotic_sound default. |
| 1.8 | Top of the knob, set by hand. |
| ≈ 2.1 | The attractor itself develops quiet spells. |

Turning $\mu$ up slows the swing; its period nearly doubles across the knob.

## Properties

- **Attractor:** two lobes, one per polarity. Cook and Roberts pictured a point wandering near a bounded two-sheeted surface, reversing where the sheets come close [4]. Kaplan–Yorke dimension ≈ 2.05 at the default.
- **Equilibria:** $(\pm k,\ \pm 1/k,\ \mu k^2)$ with $\mu k^4 - a k^2 - \mu = 0$, for every $\mu > 0$; none has zero current. Their characteristic polynomial, $(\lambda + 2\mu)(\lambda^2 + k^2 + k^{-2})$, gives a strongly attracting direction ($-2\mu$) and a linear centre in the remaining plane, with period $2\pi/\sqrt{k^2 + k^{-2}}$ (4.26 at the default). For such non-hyperbolic points the linear terms do not decide stability: Cook and Roberts showed they are "unstable foci" [4]. Numerically they repel only weakly, so an orbit left close to one lingers (`docs/studies/fifth-system-screening.md`).
- **Symmetry:** $(x, y, z) \mapsto (-x, -y, z)$. A reversed field is as good as the original.
- **Dissipation:** constant divergence $-2\mu$; at the default, volumes shrink about tenfold per time unit.
- **Lyapunov exponents:** $(0.12,\ 0,\ -2.43)$ at the default (ours; the third follows from their sum, $-2\mu$). Runs of 10,000 time units from 40 random starts give 0.116–0.125 (one start that lingered near an equilibrium aside); the catalog's shorter run reads 0.108. At $\mu = 1$ we measure 0.124–0.129, dysts 0.132.
- **Phase coherence:** high for $z$, one swing per loop on either lobe; the flips smear $x$ and $y$.
- **Boundedness:** the flow as a whole is not bounded. On the invariant $z$-axis ($x = y = 0$, no current) $\dot z = 1$: nothing brakes the discs, which speed up forever. Llibre and Messias show that some orbits escape to infinity and that, unlike Lorenz's, the attractor fits in no ellipsoid [18]. The attractor itself stayed bounded in all 80 random starts of our screening (numerical evidence only); the axis repels nearby orbits once $z(z - a) > \mu^2$.

## History

Edward Bullard, at the National Physical Laboratory, analysed a single-disc dynamo in 1955: it settles to steady spinning, oscillates about it, or (with a load in parallel with the coil) oscillates ever more widely, but never reverses [2, 3]. Tsuneji Rikitake (1921–2004) [16], of the Earthquake Research Institute in Tokyo, coupled two discs in 1958 and found reversals, "unlike the case of a single disk dynamo" [1].

The timing is striking. In 1905–06 Bernard Brunhes found lava, and the clay it had baked, magnetized the "wrong" way, and concluded that the field had once pointed the other way [9, 17]. In 1929 Motonori Matuyama found the same in basalts from Japan, Korea and Manchuria, and argued that the reversed rocks were older than the normal ones [21]. Yet neither Brunhes nor Matuyama made many converts [17]. One obstacle was self-reversal: a few rocks magnetize against the field they cool in [21]. The idea won wide acceptance only in the 1960s, when dated lavas yielded a timescale of reversals [19, 21] and when Fred Vine and Drummond Matthews (1963) [10], and independently Lawrence Morley [20], read the magnetic stripes of the sea floor as a tape recording of reversals made by spreading crust.

D. W. Allan (1962) studied systems of coupled disc dynamos; his extended numerical runs showed that a true reversal of field can occur [6]. A. E. Cook and Paul H. Roberts (1970), the latter at Newcastle, gave the geometric picture [4], a year before Ruelle and Takens coined the term "strange attractor" [11]; by 1980 "chaos" was in the title of a paper on the system [7]. It is now a textbook model of the geodynamo [8].

Roberts, by then at UCLA, went on to model the real core: in 1995, with Gary Glatzmaier, he published the first three-dimensional, self-consistent computer model of the geodynamo, and its field reversed [13, 22]. Earth's last reversal, the Brunhes–Matuyama, is usually dated to about 780,000 years ago [17]. Recent work combining dated lavas with sediment and ice-core records puts its final flip near 773,000 years ago, after about 22,000 unstable years that began near 795,000 [12]. The discs remain a cartoon of a turbulent fluid core.

## In chaotic_sound

The knob sweeps $\mu$ from 0.513 (chaos onset) to 1.8 (set by hand: the screening found quiet spells from $\mu \approx 2.1$). The default, 1.153, sits mid-knob ($u = 0.497$); the dysts value 1 sits at $u = 0.378$. Times are in system units.

- **Tuning.** The app tunes on the peak centroid of $z$, whose prominence is at least 0.46 across the range (0.53 at the default, against 0.014 for $x$ and 0.064 for $y$). At the default $P = 5.474$, so A4 runs about 2,408 time units per second. dysts lists a period of 5.90; we measure 5.12 at $\mu = 1$. Measured tuning errors average −0.3 to +1.3 cents (worst single render 5.5 cents). The demo `09_pitch_glide.wav` glides it from A1 to A5 through the pitch input.
- **How the period moves.** $P$ rises smoothly from 3.785 to 7.016 (1068 cents; no step above 1.3%). With pitch lock off, the pitch rises 6.4 semitones at the bottom and falls 4.3 at the top.
- **How chaotic it is.** $\lambda \approx 0.12$ at the default: nearby paths separate by a factor $e$ every 8.3 time units, about 1.5 swings ($\lambda P \approx 0.66$). $\lambda P$ stays near 0.65–0.70 from $\mu \approx 0.7$ to 1.5, is about 0.5–0.6 on either side, and drops to 0.22 at the very bottom. 98% of the 130 table points are chaotic.
- **Reversals.** In our own check (four runs of about 37,000 swings each at the default), the sign of $x$ held for 2.5 swings on average: about half the stretches last one swing, 0.6% last 20 or more, and the longest lasted 37 in every run. At the bottom of the knob $x$ flips on (almost) every swing, so it repeats at twice the period of $z$.
- **Level.** By the level rule (RMS 0.25 at amp = 1, unless the robust peak, the 99.9th percentile, would pass 0.8) and the catalog tables, $z$ always plays at RMS 0.25. The spikier $y$ (robust crest factor up to 4.2) is held lower, 0.22 at the default and 0.19 at the top, and so is $x$ above $\mu \approx 1.2$, down to 0.21.
- **Quiet traps.** An abrupt jump of $\mu$ can strand the state next to an equilibrium: in the screening, a square modulator with a period of 7 swings left all 8 runs quiet 7% of the time on average. Random starts can land there too (in our check, 1 of 40 at the default circled an equilibrium for about 1,300 swings). The parameter slew, at least $\max(5\text{ ms}, 2/f)$, is expected to help, but this is unmeasured for Rikitake: the screening predates the slew.

## Sound notes

To be filled in after listening tests (Phase 1).

Hypotheses, to be tested:

- *Hypothesis:* $z$ should sound clearly pitched, its loudness slightly uneven; $x$ a barely pitched texture that flips polarity every few swings.
- *Hypothesis:* near the bottom of the knob $x$ should turn pitched (prominence up to 0.84), an octave below the note.
- *Hypothesis:* a voice caught near an equilibrium should sing a faint, almost pure tone at the linear period, about 4.4 semitones above the note at the default.

## References

1. Rikitake, T. (1958). Oscillations of a system of disk dynamos. *Proceedings of the Cambridge Philosophical Society*, 54(1), 89–105. https://doi.org/10.1017/S0305004100033223
2. Bullard, E. (1955). The stability of a homopolar dynamo. *Proceedings of the Cambridge Philosophical Society*, 51(4), 744–760. https://doi.org/10.1017/S0305004100030814
3. Lowes, F. (2007). Postscripts on geodynamo's beginnings (letter). *Physics Today*, 60(7), 13–15. https://doi.org/10.1063/1.2761785
4. Cook, A. E., & Roberts, P. H. (1970). The Rikitake two-disc dynamo system. *Proceedings of the Cambridge Philosophical Society*, 68(2), 547–569. https://doi.org/10.1017/S0305004100046338
5. Nakajima, F., & Inoue, S. (2010). Modification of Rikitake's model for the geomagnetic field. *RIMS Kôkyûroku*, 1688, 39–48. https://www.kurims.kyoto-u.ac.jp/~kyodo/kokyuroku/contents/pdf/1688-05.pdf
6. Allan, D. W. (1962). On the behaviour of systems of coupled dynamos. *Proceedings of the Cambridge Philosophical Society*, 58(4), 671–693. https://doi.org/10.1017/S0305004100040718
7. Ito, K. (1980). Chaos in the Rikitake two-disc dynamo system. *Earth and Planetary Science Letters*, 51(2), 451–456. https://doi.org/10.1016/0012-821X(80)90224-1
8. Moffatt, H. K., & Dormy, E. (2019). *Self-Exciting Fluid Dynamos*, ch. 11, "Low-dimensional models of the geodynamo". Cambridge University Press. https://doi.org/10.1017/9781107588691.015
9. Kornprobst, J., & Lénat, J.-F. (2014, November 4). Centenary of the discovery of Earth's magnetic field reversals. *Eos*. https://eos.org/articles/centenary-discovery-earths-magnetic-field-reversals
10. Vine, F. J., & Matthews, D. H. (1963). Magnetic anomalies over oceanic ridges. *Nature*, 199, 947–949. https://doi.org/10.1038/199947a0
11. Ruelle, D., & Takens, F. (1971). On the nature of turbulence. *Communications in Mathematical Physics*, 20(3), 167–192. https://doi.org/10.1007/BF01646553
12. Singer, B. S., Jicha, B. R., Mochizuki, N., & Coe, R. S. (2019). Synchronizing volcanic, sedimentary, and ice core records of Earth's last magnetic polarity reversal. *Science Advances*, 5(8), eaaw4621. https://doi.org/10.1126/sciadv.aaw4621
13. Glatzmaier, G. A., & Roberts, P. H. (1995). A three-dimensional self-consistent computer simulation of a geomagnetic field reversal. *Nature*, 377, 203–209. https://doi.org/10.1038/377203a0
14. Gilpin, W. (2021). Chaos as an interpretable benchmark for forecasting and data-driven modelling. *NeurIPS Datasets and Benchmarks Track*. arXiv:2110.05266. Code: https://github.com/GilpinLab/dysts
15. Danca, M.-F., & Codreanu, S. (2011). Finding the Rikitake's attractors by parameter switching. arXiv:1102.2164. https://arxiv.org/abs/1102.2164 (Eq. 1: their $a = R\sqrt{LC/(GM)}$, proportional to the resistance $R$, is our $\mu$; their $p$ is our $a$.) Journal version: Danca, M.-F., & Codreanu, S. (2012). Modeling numerically the Rikitake's attractors by parameter switching. *Journal of the Franklin Institute*, 349(3), 861–878. https://doi.org/10.1016/j.jfranklin.2011.11.014
16. Bibliothèque nationale de France, authority record "Rikitake, Tsuneji (1921–2004)". https://catalogue.bnf.fr/ark:/12148/cb122993239
17. Linda Hall Library. Motonori Matuyama. *Scientist of the Day*. https://www.lindahall.org/about/news/scientist-of-the-day/motonori-matuyama/
18. Llibre, J., & Messias, M. (2009). Global dynamics of the Rikitake system. *Physica D*, 238(3), 241–252. https://doi.org/10.1016/j.physd.2008.10.011
19. Cox, A., Doell, R. R., & Dalrymple, G. B. (1964). Reversals of the Earth's magnetic field. *Science*, 144(3626), 1537–1543. https://doi.org/10.1126/science.144.3626.1537
20. Morley, L. W. (2001). The zebra pattern. In N. Oreskes (Ed.), *Plate Tectonics: An Insider's History of the Modern Theory of the Earth* (ch. 4). Westview Press. (Morley's own account; located, not read: the scan has no text layer. His independent proposal is also described in Wikipedia's "Vine–Matthews–Morley hypothesis" article.)
21. Kono, M. (2024). Motonori Matuyama and reversals of geomagnetic field. *Proceedings of the Japan Academy, Series B*, 100(9), 491–499. https://doi.org/10.2183/pjab.100.031
22. Soward, A. M. (2023). Paul Harry Roberts. 13 September 1929—17 November 2022. *Biographical Memoirs of Fellows of the Royal Society*, 76, 365–387. https://doi.org/10.1098/rsbm.2023.0019 (abstract read)
