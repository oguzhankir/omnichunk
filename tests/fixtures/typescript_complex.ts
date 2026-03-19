type Request = { params: { id: string } };
type Response = { json: (value: unknown) => void };

class Logger {
  info(message: string): void {
    console.log(message);
  }
}

interface User {
  id: string;
  email: string;
}

export class UserService {
  constructor(private readonly logger: Logger) {}

  async getUser(id: string): Promise<User | null> {
    this.logger.info(`getUser:${id}`);
    return { id, email: `${id}@example.com` };
  }

  async deleteUser(id: string): Promise<boolean> {
    this.logger.info(`deleteUser:${id}`);
    return true;
  }
}

export async function handleGet(req: Request, res: Response) {
  const svc = new UserService(new Logger());
  const user = await svc.getUser(req.params.id);
  res.json(user);
}
