# Physical RP matrix — store release

Physical claims require a real iPhone and a real Android device. Simulator/Maestro PASS is not physical proof.

**Devices required:** one iPhone (Face ID if available) + one Android (biometrics if available)  
**Build:** store/canary native build of `ai.wathefni.employee` pointed at `https://api.wathefni.ai`

| ID | Proof | iPhone | Android |
|---|---|---|---|
| PH-1 | Keyboard: focused input stays visible | | |
| PH-2 | Keyboard: bottom actions still reachable | | |
| PH-3 | Android keyboard avoidance | n/a | |
| PH-4 | PIN / assistant keyboard offsets | | |
| PH-5 | Face ID / biometrics enrol, unlock, fallback, revoke | | |
| PH-6 | PIN create / unlock / lockout / recovery | | |
| PH-7 | Camera capture + file picker + native viewer | | |
| PH-8 | Push delivery while backgrounded | | |
| PH-9 | HTTPS App Link `https://api.wathefni.ai/l/leave` opens Leave when installed; store fallback when not | | |
| PH-10 | Privacy cover, offline/reconnect, foreground refresh | | |
| PH-11 | Real RTL rendering (AR) | | |

Mark each cell **PASS**, **FAIL**, or **UNPROVEN**. Never infer from simulator.

If either device is absent, the store stamp stays blocked with **only this physical gate outstanding** once every automated gate is green.
