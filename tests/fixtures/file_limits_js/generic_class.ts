export class Store<T extends { id: string }> extends Base<{ size: number }> {
  find(id: string): T | undefined {
    for (const item of this.items) {
      if (item.id === id) return item;
    }
    return undefined;
  }
}
