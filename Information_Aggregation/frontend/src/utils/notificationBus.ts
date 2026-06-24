type NotificationHandler = (event?: unknown) => void

const handlers = new Set<NotificationHandler>()

export const notificationBus = {
  emit(event?: unknown) {
    handlers.forEach((handler) => handler(event))
  },
  on(handler: NotificationHandler) {
    handlers.add(handler)
    return () => {
      handlers.delete(handler)
    }
  },
}
