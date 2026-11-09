/**
 * Browser extensions (translators, AI sidebars) move or wrap text nodes React owns, which makes
 * React's removeChild/insertBefore throw "The node to be removed is not a child of this node" and
 * crash the page. This makes those two calls tolerant. Call once on the client.
 */
let done = false;
export function installDomGuard() {
  if (done || typeof window === "undefined" || typeof Node === "undefined") return;
  done = true;
  const remove = Node.prototype.removeChild;
  Node.prototype.removeChild = function <T extends Node>(this: Node, child: T): T {
    if (child.parentNode !== this) {
      if (child.parentNode) child.parentNode.removeChild(child);
      return child;
    }
    return remove.call(this, child) as T;
  };
  const insert = Node.prototype.insertBefore;
  Node.prototype.insertBefore = function <T extends Node>(this: Node, node: T, ref: Node | null): T {
    if (ref && ref.parentNode !== this) return insert.call(this, node, null) as T;
    return insert.call(this, node, ref) as T;
  };
}
