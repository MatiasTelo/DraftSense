/**
 * Las cinco rutas públicas (`docs/30-ux-flujos.md` §2).
 *
 * El camino principal es `/` → `/start` → `/play` y termina ahí. Perfil y tabla de posiciones son
 * ramas laterales a las que se llega desde la barra inferior durante el juego, y de las que
 * siempre se vuelve con un botón grande.
 *
 * `/admin` no se enlaza desde ninguna parte y llega en la semana 7, con `docs/24-panel-admin.md`.
 */

import { useEffect } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { Landing } from './screens/Landing';
import { Leaderboard } from './screens/Leaderboard';
import { Onboarding } from './screens/Onboarding';
import { Play } from './screens/Play';
import { Profile } from './screens/Profile';
import { useSession } from './store/session';

export default function App() {
  const bootstrap = useSession((state) => state.bootstrap);

  // `POST /sessions` al arrancar. No hace falta para poder responder —los endpoints que necesitan
  // identidad crean la sesión al vuelo (`docs/12-api.md` §1.3)— pero es lo que da
  // `onboarding_seen`, que es con lo que el landing decide entre `Start` y `Continue`.
  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/start" element={<Onboarding />} />
      <Route path="/play" element={<Play />} />
      <Route path="/me" element={<Profile />} />
      <Route path="/leaderboard" element={<Leaderboard />} />
      {/* Una ruta desconocida vuelve al landing, que resuelve solo a dónde ir. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
