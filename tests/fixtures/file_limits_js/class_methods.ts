export abstract class Store<T> extends Base implements Disposable {
  private items: T[] = [];
  static readonly label = "store {";

  constructor(private readonly name: string) {
    super();
  }

  abstract key(item: T): string;

  public async add(item: T): Promise<void> {
    this.items.push(item);
  }

  get size(): number {
    return this.items.length;
  }

  #reset() {
    function clear(list: unknown[]) {
      list.length = 0;
    }
    clear(this.items);
  }

  onChange = (item: T) => {
    this.add(item);
  };
}
