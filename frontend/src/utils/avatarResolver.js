const avatarModules = import.meta.glob('../assets/avatars/Agent_*.svg', { eager: true, query: '?url', import: 'default' })

const avatarList = Object.entries(avatarModules)
  .sort(([a], [b]) => {
    const numA = parseInt(a.match(/Agent_(\d+)/)?.[1] || '0', 10)
    const numB = parseInt(b.match(/Agent_(\d+)/)?.[1] || '0', 10)
    return numA - numB
  })
  .map(([, url]) => url)

export const totalAvatars = avatarList.length

export function getAvatarUrl(index) {
  if (avatarList.length === 0) return null
  return avatarList[index % avatarList.length]
}
