export class Bag<T> {
  #items: T[] = [];
  [key: string]: unknown;
  [Symbol.iterator]() {
    let i = 0;
    const items = this.#items;
    return { next: () => ({ done: i >= items.length, value: items[i++] }) };
  }
  static async *["load" + "All"](src: string) {
    yield src;
  }
  [
    Symbol.toStringTag
  ] = () => "Bag";
  get [Symbol.species]() {
    return Bag;
  }
  'my-key'(x: number) {
    return x;
  }
  404() {
    return "missing";
  }
}
