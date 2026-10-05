import * as path from 'path';

/**
 * PathValidator enforces strict workspace boundary containment.
 * Prevents directory traversal attacks ('../') and unauthorized filesystem access.
 */
export class PathValidator {
  /**
   * Validates if a target path is strictly contained within any allowed workspace root.
   */
  public static isWithinWorkspace(targetPath: string, workspaceRoots: string[]): boolean {
    if (!targetPath || !workspaceRoots || workspaceRoots.length === 0) {
      return false;
    }

    const resolvedTarget = path.resolve(targetPath);

    for (const root of workspaceRoots) {
      const resolvedRoot = path.resolve(root);
      const relative = path.relative(resolvedRoot, resolvedTarget);

      // If relative starts with '..' or is absolute, it's outside the root
      if (!relative.startsWith('..') && !path.isAbsolute(relative)) {
        return true;
      }
      if (relative === '') {
        return true; // Root itself
      }
    }

    return false;
  }

  /**
   * Sanitizes and resolves a potentially untrusted relative path against a primary workspace root.
   * Throws an Error if traversal is detected.
   */
  public static resolveSafePath(relativePath: string, workspaceRoot: string): string {
    const resolvedRoot = path.resolve(workspaceRoot);
    const resolvedTarget = path.resolve(resolvedRoot, relativePath);

    const relative = path.relative(resolvedRoot, resolvedTarget);
    if (relative.startsWith('..') || path.isAbsolute(relative)) {
      throw new Error(`Path traversal blocked: '${relativePath}' escapes workspace root '${workspaceRoot}'`);
    }

    return resolvedTarget;
  }
}
