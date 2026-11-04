"""Explicit extension placeholders. No PyTorch installation is needed yet."""


class PUCTSelection:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("PUCT selection is reserved for a later implementation")


class ProgressiveWidening:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Progressive widening is reserved for a later implementation")


class PyTorchPolicyValue:
    """Future torch.nn.Module adapter implementing policies.PolicyValueModel."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("PyTorch policy/value networks are not implemented yet")


class BatchedInference:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Batched inference and pending-visit accounting are not implemented yet")
