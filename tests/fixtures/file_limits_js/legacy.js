function Legacy(name) {
  this.name = name;
}

Legacy.prototype.greet = function greet() {
  return "hi " + this.name;
};

var double = (x) => {
  return x * 2;
};

class Modern extends Legacy {
  greet() {
    return super.greet() + "!";
  }
}
