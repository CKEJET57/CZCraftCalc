import { Route, Routes, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { HomePage } from './pages/HomePage'
import { BatchPage } from './pages/BatchPage'
import { ItemPage } from './pages/ItemPage'
import { CharacterPage } from './pages/CharacterPage'
import { TopItemsPage } from './pages/TopItemsPage'
import { api } from './api/client'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="recipe" element={<Navigate to="/items" replace />} />
        <Route path="batch" element={<BatchPage />} />
        <Route path="items" element={<ItemPage />} />
        <Route path="top-items" element={<TopItemsPage />} />
        <Route path="character" element={api.desktop ? <Navigate to="/" replace /> : <CharacterPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
