import { createRouter, createWebHashHistory } from 'vue-router'
import Replay from '@/views/game2d/Replay.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      redirect: '/replay/sample',
    },
    {
      path: '/replay/:gameId',
      name: 'replay',
      component: Replay,
      props: true,
    },
  ],
})

export default router
