import { Route, Routes } from 'react-router-dom';

import { Layout } from './components/Layout';
import Audit from './screens/Audit';
import Connectivity from './screens/Connectivity';
import Coverage from './screens/Coverage';
import Exports from './screens/Exports';
import Jobs from './screens/Jobs';
import Overview from './screens/Overview';
import Patches from './screens/Patches';
import Pool from './screens/Pool';
import Quality from './screens/Quality';
import Settings from './screens/Settings';

/** Las diez vistas de `docs/24-panel-admin.md` §2. */
export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/conectividad" element={<Connectivity />} />
        <Route path="/cobertura" element={<Coverage />} />
        <Route path="/calidad" element={<Quality />} />
        <Route path="/pool" element={<Pool />} />
        <Route path="/parametros" element={<Settings />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/parches" element={<Patches />} />
        <Route path="/exportaciones" element={<Exports />} />
        <Route path="/auditoria" element={<Audit />} />
        <Route path="*" element={<Overview />} />
      </Routes>
    </Layout>
  );
}
