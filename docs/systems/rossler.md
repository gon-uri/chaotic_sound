<!-- Draft written by an AI agent; facts need human review before publishing. Last updated: 2026-10-25 -->

# Rössler system

> A deliberately minimal recipe for chaos: a slow outward spiral, a sudden lift, a drop back to the centre, and a tone that almost repeats but never quite does.

## In plain words

Picture a marble circling in a dish that gently pushes it outward, so each lap is a little wider than the last. When a lap gets wide enough, a third ingredient flips the marble up and over and drops it back near the centre, and the slow spiral starts again. The landing spot is never quite the same, so the next run of laps is never quite the same either. The spiral stretches neighbouring paths apart, and the flip folds the stretched band back over itself, the way a taffy-pulling machine works candy.

For a musician, the key point is that every lap takes almost the same time. One lap is one cycle of the waveform, and by our measurements this is the most clearly pitched system in the app. What wanders is the size of each lap. So we expect the chaos to sound less like noise and more like an irregular breathing on top of a clear note (still to be confirmed by listening).

## Equations

$$
\begin{aligned}
\dot{x} &= -y - z\\
\dot{y} &= x + a\,y\\
\dot{z} &= b + z\,(x - c)
\end{aligned}
$$

- $x$ and $y$ are the rotating pair. With $z = 0$ they form an oscillator that turns about once every $2\pi$ time units while slowly spiralling outward.
- $z$ acts as a switch. It stays near zero for most of each lap and fires a short, tall spike when $x$ climbs above $c$. The spike throws the orbit back towards the centre, through the $-z$ in $\dot x$.
- $a = 0.2$ sets how fast the spiral unwinds.
- $b = 0.2$ is a small constant feed into $z$, which keeps $z$ positive.
- $c = 5.7$ is the firing threshold (the knob).

There is only one nonlinear term, $zx$; Lorenz's system has two.

**dysts compared with the original.** dysts uses Rössler's form with $a = b = 0.2$ and $c = 5.7$, citing his 1976 letter [1, 19]. These are the values Rössler himself gives when he recalls finding the system [3, 5]. Later work often uses other values (the Scholarpedia article, for instance, uses $a = 0.432$, $b = 2$, $c = 4$ [5]). Although the model was inspired by chemistry, $x$ and $y$ go negative, so they are not concentrations: it is an abstract prototype.

## The parameter you control: $c$

$c$ sets how wide the spiral may grow before the switch fires, so raising it makes the laps larger and the $z$ spikes taller. With $a = b = 0.2$, increasing $c$ gives the textbook period-doubling route to chaos [18]:

| $c$ | What happens ($a = b = 0.2$) |
|---|---|
| below ≈ 2.83 | One simple loop (period 1), e.g. $c = 2.5$. |
| ≈ 2.8324 | First period doubling, proved with computer assistance [15]. Two alternating laps (e.g. $c = 3.5$). |
| ≈ 3.8374 | Second period doubling (period 4, e.g. $c = 4$), also proved in [15]. |
| ≈ 4.1 | Period 8, then ever faster doublings. |
| ≈ 4.2 | The cascade accumulates. Chaos first appears in 4 and then 2 separate bands, which merge into a single band at $c \approx 4.5$. |
| ≈ 5.19–5.5 | Period-3 window: period 3, then doublings to 6 and 12, then chaos again. |
| 5.7 | Rössler's classical value. |
| ≈ 8.1 and above | Some small laps stop circling the centre: the attractor becomes partly "funnel"-like. |

The first two doubling values are from the literature [15]. The others come from our own simulations, not from a published table. The pattern of doublings, band mergings and windows is the one familiar from one-hump maps such as the logistic map. Plot each maximum of $x$ against the next and the points fall close to a single humped curve [5, 20].

## Properties

- **Attractor:** a single band that is stretched, folded and laid back on itself, not the two wings of Lorenz [5]. It is extremely thin. Its Kaplan–Yorke dimension is about 2.01 (2.013 from the exponents below; dysts gives 2.015), so it is nearly a surface.
- **Equilibria:** there are two, at $(a z_\pm,\ -z_\pm,\ z_\pm)$ with $z_\pm = \big(c \pm \sqrt{c^2 - 4ab}\big)/(2a)$.
  - The inner one, at about $(0.007, -0.035, 0.035)$, is the centre of the spiral. It is a saddle-focus with eigenvalues of about $0.097 \pm 0.995i$ and $-5.69$.
  - The outer one, at about $(5.69, -28.5, 28.5)$, lies far outside the attractor.
- **Symmetry:** none, so there is no mirror lobe.
- **Dissipation:** the divergence is $a + x - c$, which varies along the orbit. Its average is about $-5.32$ per time unit, the sum of the Lyapunov exponents.
- **Lyapunov exponents:**
  - This project measures $\lambda \approx 0.068$.
  - Kuptsov and Kuznetsov give $(0.072,\ \approx 0,\ -5.394)$ [16]. Our own spectrum computation agrees.
  - dysts lists $\lambda_{\max} \approx 0.15$, about twice the other estimates, but its own spectrum estimate starts at 0.076 [19].
  - Per lap, $\lambda P \approx 0.4$, so nearby paths separate by about ×1.5 per lap. Lorenz is about 0.7 per loop (0.6–0.7 across its range).
- **Phase coherence:**
  - At the default, the $x$–$y$ motion always turns the same way around the inner equilibrium. The angle around that centre is therefore a good phase and grows almost uniformly, which gives a sharp spectral peak on a broad base.
  - The Santa Cruz group studied this system's spectra in 1980 [9] and named the property "phase coherence" in a companion paper [10]. It made Rössler the standard model for phase synchronization: two coupled Rössler oscillators can lock their phases while their amplitudes stay chaotic [11, 12].
  - If small loops start to miss the centre, the attractor becomes a non-coherent "funnel", in which the phase is ill-defined and the peak broadens [12, 13]. That literature usually reaches it by raising $a$ (exact parameter values unverified). In our simulations at $a = b = 0.2$, a few percent of laps already miss the centre from $c \approx 8.1$.
- **Boundedness and rigour:**
  - $z$ never goes negative, since $\dot z = b > 0$ at $z = 0$.
  - The attractor is bounded, but some starting points and parameter values send orbits to infinity [17].
  - A computer-assisted proof shows that the classical system contains chaotic symbolic dynamics [14].

## History

**A medical graduate with an analog computer.** Otto E. Rössler, born in Berlin in 1940 (unverified), studied medicine but never practised it [3]. He then worked at the Max Planck Institute for Behavioural Physiology in Seewiesen, where he befriended the ethologist Konrad Lorenz (no relation of Edward). In 1970 he joined Friedrich-Franz Seelig's group in Tübingen. There an analog computer, a Dornier DO 240, let him wire up small reaction schemes like electronic circuits [3].

**Winfree's challenge.** At a chronobiology meeting in Vienna in 1975, Rössler described to the biologist Arthur Winfree a three-variable limit cycle shaped like a knot. Winfree said it sounded like chaos. Fresh from a meeting on chaos in Aspen, Winfree mailed him a folder of papers a few weeks later, including Lorenz's 1963 paper, and asked for a chemical version of the Lorenz attractor [3, 4].

**The 1976 papers.** Rössler did not find a chemical Lorenz attractor, so he settled for something simpler [3, 5]. In 1976 he published a paper on chaos in simple reaction models [2] and a two-page letter in *Physics Letters A* giving the equation now named after him [1]. He recalls starting from an image of a rope wrapped around his nose that falls off and loops back [3, 5]. His accounts of the next step differ: in 2021 he describes turning the analog computer's knobs and simplifying [3], in 2006 the simplified equations taking shape on a slow HP 9820A desktop computer [5]. To explain the stretching and folding he used a taffy-pulling machine; Ulrich Parlitz remembers his taffy-puller slides at a seminar in Göttingen [3]. Igra traces the inspiration to Rössler's 1983 paper [6, 20], which we have not checked. Soon after, Lars Folke Olsen and Hans Degn found chaos in a real enzyme reaction. Olsen had visited Rössler in Tübingen, and when he described his irregular oscillations, Rössler told him to read Lorenz [3, 8].

**The sound of chaos.** With Reimara Waible, Rössler made a film on the analog computer with the "sound of chaos", a title that plays on Simon and Garfunkel's "The Sound of Silence". He recalls that the sound was "familiar to the ear", and he took that as a sign that chaos is close to everyday life [3].

**Name and legacy.** Rössler credits Norman Packard, Rob Shaw, Jim Crutchfield and Doyne Farmer of Santa Cruz with coining the name "Rössler attractor" [3]. In 1979 he used a four-variable system to introduce hyperchaos, chaos with two positive Lyapunov exponents [7]. The 1976 system went on to become a textbook example of period doubling [18], the workhorse of phase synchronization [11] and a test bed for computer-assisted proofs [14, 15].

## In chaotic_sound

- **The knob** sweeps $c$ from 5.5125 to 8.8184, with the default 5.7 near the bottom. The project calls a grid point chaotic when $\lambda P > 0.05$. By that test 82% of the 33 grid points are chaotic, and $\lambda = 0.068$ at the default.
- **Tuning.** The app tunes from $x$, which has a very sharp spectral peak (prominence ≈ 0.83). The main period at the default is $P = 5.8556$ time units. To play $f_0$, the engine advances $k = P \cdot f_0$ time units per second, about 2,576 for A4 = 440 Hz.
- **An almost fixed period.** Across the range the period only moves between 5.739 and 5.924, about 3% (roughly 55 cents). A likely reason is that the turning rate comes from the $x$–$y$ oscillator, which does not contain $c$. So the knob changes the pitch very little; we expect it to change mainly the colour and roughness of the sound (to be confirmed by listening).
- **Periodic windows.** A finer sweep (241 values, spacing 0.0375) found spots inside the range where $\lambda P < 0.05$: single points at $c \approx 5.89$, 6.0, 7.275, 7.35 and 7.725, and stretches at 6.675–6.825 and 7.875–8.1. Some are truly periodic, repeating exactly after a fixed number of laps (e.g. 4 laps at 6.675, 5 around 8.0). Others (≈ 5.89, 6.0 and the 6.825 edge) are very weakly chaotic and only almost repeat. An $n$-lap cycle adds spectral lines at $1/n$ of the main pitch, so there we expect the roughness to fade and lower lines to appear.
- **Range ends.** The low end sits just above the period-3 window (which the sweep flagged at $c \approx 5.21$). The high end is trimmed just before $c \approx 8.9$, where the measured period would jump. By then the attractor is already partly funnel-like, since from about $c \approx 8.1$ some laps miss the centre.
- Numbers are in the system's own time units.

## Sound notes

To be filled in after listening tests (Phase 1).

Hypotheses (to be tested):

- $x$ should be the most clearly pitched box: a near-pure tone whose loudness breathes irregularly, rather than one that hisses. The reasons are its very sharp peak (prominence ≈ 0.83) and its slow chaos ($\lambda P \approx 0.4$).
- $z$, if exposed, should sound buzzy and bright at the same pitch, since it is a train of narrow spikes.
- Raising $c$ should roughen the tone with little pitch change. In the truly periodic windows (6.675–6.8 and 7.875–8.1) the tone should turn steady, possibly with an audible subharmonic. Above $c \approx 8.1$, where some laps skip the centre, the pitch may sound a little less clean.

## References

1. Rössler, O. E. (1976). An equation for continuous chaos. *Physics Letters A*, 57(5), 397–398. https://doi.org/10.1016/0375-9601(76)90101-8
2. Rössler, O. E. (1976). Chaotic behavior in simple reaction systems. *Zeitschrift für Naturforschung A*, 31(3–4), 259–264. https://doi.org/10.1515/zna-1976-3-408
3. Letellier, C., Abraham, R., Shepelyansky, D. L., Rössler, O. E., et al. (2021). Some elements for a history of the dynamical systems theory. *Chaos*, 31(5), 053110. Section IV, "My Dance with Chaos", is by O. E. Rössler; Section XII is by U. Parlitz. https://doi.org/10.1063/5.0047851
4. Letellier, C., & Messager, V. (2010). Influences on Otto E. Rössler's earliest paper on chaos. *International Journal of Bifurcation and Chaos*, 20(11), 3585–3616. https://doi.org/10.1142/S0218127410027854
5. Letellier, C., & Rössler, O. E. (2006). Rössler attractor. *Scholarpedia*, 1(10), 1721. Includes Rössler's own reminiscences. https://doi.org/10.4249/scholarpedia.1721
6. Rössler, O. E. (1983). The chaotic hierarchy. *Zeitschrift für Naturforschung A*, 38(7), 788–801. https://doi.org/10.1515/zna-1983-0714 (Cited by Igra [20] for the taffy-puller inspiration; not checked in the original.)
7. Rössler, O. E. (1979). An equation for hyperchaos. *Physics Letters A*, 71(2–3), 155–157. https://doi.org/10.1016/0375-9601(79)90150-6
8. Olsen, L. F., & Degn, H. (1977). Chaos in an enzyme reaction. *Nature*, 267, 177–178. https://doi.org/10.1038/267177a0
9. Crutchfield, J. P., Farmer, J. D., Packard, N. H., Shaw, R. S., Jones, G., & Donnelly, R. J. (1980). Power spectral analysis of a dynamical system. *Physics Letters A*, 76(1), 1–4. https://doi.org/10.1016/0375-9601(80)90130-9
10. Farmer, J. D., Crutchfield, J. P., Froehling, H., Packard, N. H., & Shaw, R. S. (1980). Power spectra and mixing properties of strange attractors. *Annals of the New York Academy of Sciences*, 357, 453–471. https://doi.org/10.1111/j.1749-6632.1980.tb29710.x
11. Rosenblum, M. G., Pikovsky, A. S., & Kurths, J. (1996). Phase synchronization of chaotic oscillators. *Physical Review Letters*, 76(11), 1804–1807. https://doi.org/10.1103/PhysRevLett.76.1804
12. Pikovsky, A., Rosenblum, M., & Kurths, J. (2001). *Synchronization: A Universal Concept in Nonlinear Sciences*. Cambridge University Press. https://doi.org/10.1017/CBO9780511755743
13. Osipov, G. V., Hu, B., Zhou, C., Ivanchenko, M. V., & Kurths, J. (2003). Three types of transitions to phase synchronization in coupled chaotic oscillators. *Physical Review Letters*, 91(2), 024101. https://doi.org/10.1103/PhysRevLett.91.024101
14. Zgliczyński, P. (1997). Computer assisted proof of chaos in the Rössler equations and in the Hénon map. *Nonlinearity*, 10(1), 243–252. https://doi.org/10.1088/0951-7715/10/1/016
15. Wilczak, D., & Zgliczyński, P. (2009). Period doubling in the Rössler system—a computer assisted proof. *Foundations of Computational Mathematics*, 9(5), 611–649. https://doi.org/10.1007/s10208-009-9040-x (preprint: arXiv:0712.1123)
16. Kuptsov, P. V., & Kuznetsov, S. P. (2018). Lyapunov analysis of strange pseudohyperbolic attractors: angles between tangent subspaces, local volume expansion and contraction. *Regular and Chaotic Dynamics*, 23(7–8), 908–932. https://doi.org/10.1134/S1560354718070079
17. Barrio, R., Blesa, F., & Serrano, S. (2014). Unbounded dynamics in dissipative flows: Rössler model. *Chaos*, 24(2), 024407. https://doi.org/10.1063/1.4871712
18. Strogatz, S. H. (2024). *Nonlinear Dynamics and Chaos* (3rd ed.). CRC Press. https://doi.org/10.1201/9780429398490
19. Gilpin, W. (2021). Chaos as an interpretable benchmark for forecasting and data-driven modelling. *NeurIPS Datasets and Benchmarks Track*. arXiv:2110.05266. Code and metadata: https://github.com/GilpinLab/dysts
20. Igra, E. (2023/2024). One dimensional dynamics and the Rössler attractor. arXiv:2312.13840. https://arxiv.org/abs/2312.13840
